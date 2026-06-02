from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

from .interview_store import InterviewStore


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_csv(url: str, *, timeout: float = 60.0) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text
        if text.lstrip().startswith("<!DOCTYPE") or "<html" in text[:200].lower():
            raise RuntimeError(
                "Sheet returned HTML (login page). Ensure link sharing is "
                "'Anyone with the link' can view."
            )
        return text


def normalize_row(raw: dict[str, str], field_map: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, header in field_map.items():
        val = raw.get(header, "")
        val = val.strip() if isinstance(val, str) else val
        out[key] = val or None
    return out


def parse_rows(csv_text: str, field_map: dict[str, str]) -> list[dict[str, Any]]:
    reader = csv.DictReader(StringIO(csv_text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if not any((v or "").strip() for v in raw.values()):
            continue
        question = (raw.get(field_map["question"]) or "").strip()
        if not question:
            continue
        rows.append(normalize_row(raw, field_map))
    return rows


def write_json_snapshot(
    out_path: Path,
    *,
    cfg: dict,
    rows: list[dict[str, Any]],
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": {
            "spreadsheet_id": cfg["spreadsheet_id"],
            "tab": cfg["interview_questions_tab"],
            "url": cfg["spreadsheet_url"],
        },
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "questions": rows,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def run_sync(
    *,
    config_path: Path,
    store: InterviewStore,
    trigger: str,
    json_snapshot_path: Path | None = None,
) -> dict:
    """Pull sheet → upsert into DB → optionally write JSON snapshot. Returns stats dict."""
    started = time.perf_counter()
    sync_id = store.begin_sync(trigger=trigger)
    try:
        cfg = load_config(config_path)
        csv_text = fetch_csv(cfg["export_csv_url"])
        rows = parse_rows(csv_text, cfg["column_map"])
        upsert_stats = store.upsert_many(rows)
        if json_snapshot_path is not None:
            write_json_snapshot(json_snapshot_path, cfg=cfg, rows=rows)
        duration_ms = int((time.perf_counter() - started) * 1000)
        store.end_sync(
            sync_id,
            status="success",
            fetched_rows=len(rows),
            inserted=upsert_stats["inserted"],
            updated=upsert_stats["updated"],
            unchanged=upsert_stats["unchanged"],
            duration_ms=duration_ms,
        )
        return {
            "status": "success",
            "sync_id": sync_id,
            "fetched_rows": len(rows),
            **upsert_stats,
            "inserted_row_keys": upsert_stats.get("inserted_row_keys", []),
            "updated_row_keys": upsert_stats.get("updated_row_keys", []),
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        store.end_sync(
            sync_id,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
        raise
