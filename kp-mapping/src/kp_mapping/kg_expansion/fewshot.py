from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import KgExpansionStore

REPO_ROOT = Path(__file__).resolve().parents[4]
FEWSHOT_PATH = REPO_ROOT / "evals" / "kg_expansion" / "fewshot_curriculum.json"
EVAL_SEED_PATH = REPO_ROOT / "evals" / "kg_expansion" / "seed.jsonl"

FEWSHOT_UPDATE_THRESHOLD = int(
    os.environ.get("KG_EXPANSION_FEWSHOT_UPDATE_THRESHOLD", "5")
)

logger = logging.getLogger("kp_mapping.kg_expansion.fewshot")


@lru_cache(maxsize=1)
def load_fewshot() -> dict:
    if not FEWSHOT_PATH.is_file():
        return {}
    with FEWSHOT_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def format_fewshot_for_prompt() -> str:
    data = load_fewshot()
    if not data:
        return ""
    return json.dumps(data, indent=2)


def load_eval_seed_rows() -> list[dict]:
    if not EVAL_SEED_PATH.is_file():
        return []
    rows: list[dict] = []
    with EVAL_SEED_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def maybe_update_fewshot(expansion_store: KgExpansionStore) -> bool:
    """Append reviewer rejection patterns to fewshot_curriculum.json if threshold met.

    Returns True if fewshot was updated. Uses fewshot file mtime as the
    "last updated" watermark so the threshold counts rejections since last write.
    """
    last_updated: str | None = None
    if FEWSHOT_PATH.is_file():
        import datetime
        mtime = FEWSHOT_PATH.stat().st_mtime
        last_updated = datetime.datetime.fromtimestamp(
            mtime, tz=datetime.timezone.utc
        ).isoformat()

    new_count = expansion_store.count_new_feedback_since(last_updated)
    if new_count < FEWSHOT_UPDATE_THRESHOLD:
        return False

    rejection_patterns = expansion_store.get_rejection_patterns(limit=30)
    if not rejection_patterns:
        return False

    # Load current fewshot data, append rejection labels to bad_patterns sections.
    data = load_fewshot() or {}
    updated = _merge_rejections_into_fewshot(data, expansion_store)
    if not updated:
        return False

    try:
        with FEWSHOT_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        load_fewshot.cache_clear()
        logger.info(
            "Fewshot curriculum updated with %d new rejection patterns", new_count
        )
        return True
    except Exception as exc:
        logger.exception("Failed to write fewshot curriculum: %s", exc)
        return False


def _merge_rejections_into_fewshot(
    data: dict, expansion_store: KgExpansionStore
) -> bool:
    """Append rejected KP labels into the bad_new_kps_over_granular / bad_new_kps_missing_prereqs
    sections of the fewshot data dict in-place. Returns True if any changes were made.
    """
    from collections import defaultdict

    with expansion_store._connect() as conn:
        rows = conn.execute(
            """
            SELECT feedback_type, proposed_kp_label
            FROM kg_expansion_feedback
            WHERE human_verdict = 'rejected' AND proposed_kp_label IS NOT NULL
            ORDER BY id DESC
            LIMIT 100
            """,
        ).fetchall()

    if not rows:
        return False

    # Group labels by feedback_type
    by_type: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        ft = r["feedback_type"] or "general"
        lb = (r["proposed_kp_label"] or "").strip()
        if lb:
            by_type[ft].append(lb)

    changed = False
    # Append over_granular rejections to bad_new_kps_over_granular list
    for ft, labels in by_type.items():
        key = _feedback_type_to_fewshot_key(ft)
        if key is None:
            continue
        existing = data.get(key) or []
        if not isinstance(existing, list):
            continue
        existing_labels = {
            (e.get("label") or "").lower()
            for e in existing
            if isinstance(e, dict)
        }
        for lb in labels:
            if lb.lower() not in existing_labels:
                existing.append({"label": lb})
                existing_labels.add(lb.lower())
                changed = True
        data[key] = existing

    return changed


def _feedback_type_to_fewshot_key(feedback_type: str) -> str | None:
    mapping = {
        "over_granular": "bad_new_kps_over_granular",
        "missing_prereq": "bad_new_kps_missing_prereqs",
        "prereq_dump": "bad_new_kps_prereq_dump",
    }
    return mapping.get(feedback_type)
