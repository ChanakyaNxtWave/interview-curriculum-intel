"""Promote pending coding_question content_mappings to 'approved' when the
LLM tag already passed both quality gates (overall_confidence='high' AND
needs_human_review=false).

Idempotent: only touches rows currently in 'pending'. Skips anything the
reviewer has actively moved to needs_review / rejected.

Usage:
    python scripts/bulk_approve_coding.py --dry-run
    python scripts/bulk_approve_coding.py
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


DEFAULT_DB = (
    Path(__file__).resolve().parent.parent / "data" / "kp_mappings.db"
)


WHERE = """
WHERE content_type = 'coding_question'
  AND review_status = 'pending'
  AND json_extract(ai_result_json, '$.overall_confidence') = 'high'
  AND (
      COALESCE(json_extract(ai_result_json, '$.needs_human_review'), 0) = 0
      OR json_extract(ai_result_json, '$.needs_human_review') = 'false'
  )
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT content_id, title FROM content_mappings {WHERE}").fetchall()
        print(f"Found {len(rows)} candidates for auto-approval.")
        if args.dry_run:
            for r in rows[:10]:
                print(f"  {r['content_id']}  {r['title']}")
            if len(rows) > 10:
                print(f"  ... ({len(rows) - 10} more)")
            return
        cur = conn.execute(
            f"UPDATE content_mappings SET review_status = 'approved', updated_at = datetime('now') {WHERE}"
        )
        print(f"Approved {cur.rowcount} rows.")


if __name__ == "__main__":
    main()
