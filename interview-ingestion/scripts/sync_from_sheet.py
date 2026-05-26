#!/usr/bin/env python3
"""Pull interview questions from the public Google Sheet assessments tab."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
CONFIG_PATH = REPO_ROOT / "config" / "interview_sheet.json"
DEFAULT_OUT = ROOT / "data" / "interview_questions.json"


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_csv(url: str) -> str:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text
        if text.lstrip().startswith("<!DOCTYPE") or "<html" in text[:200].lower():
            raise RuntimeError(
                "Sheet returned HTML (login page). Ensure link sharing is "
                "'Anyone with the link' can view."
            )
        return text


def normalize_row(raw: dict[str, str], field_map: dict[str, str]) -> dict:
    out: dict[str, str | None] = {}
    for key, header in field_map.items():
        val = raw.get(header, "")
        val = val.strip() if isinstance(val, str) else val
        out[key] = val or None
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync interview questions from Google Sheet")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-sample", type=int, default=0, help="Print first N rows")
    args = parser.parse_args()

    cfg = load_config(args.config)
    url = cfg["export_csv_url"]
    field_map = cfg["column_map"]

    print(f"Fetching: {cfg['interview_questions_tab']} tab...")
    csv_text = fetch_csv(url)

    reader = csv.DictReader(StringIO(csv_text))
    rows: list[dict] = []
    for raw in reader:
        if not any((v or "").strip() for v in raw.values()):
            continue
        question = (raw.get(field_map["question"]) or "").strip()
        if not question:
            continue
        rows.append(normalize_row(raw, field_map))

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

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(rows)} questions to {args.out}")

    if args.print_sample:
        for row in rows[: args.print_sample]:
            print("---")
            print(f"UUID: {row.get('question_uuid')}")
            print(f"Company: {row.get('company_name')} | Type: {row.get('question_type')}")
            print(f"Q: {(row.get('question') or '')[:120]}...")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
