#!/usr/bin/env python3
"""One-shot migration: move CODING rows out of the shared theory tables into the
dedicated coding tables.

  theory_question_tags  (question_type='CODING')  -> coding_question_tags
  theory_tag_history    (question_type='CODING')  -> coding_tag_history

Idempotent:
  - tags are keyed by UNIQUE(row_key) -> INSERT OR IGNORE, safe to re-run.
  - history has no natural key -> copied only while the coding history table is
    empty (a re-run after the originals are deleted finds nothing to copy).
After copying, the CODING rows are deleted from the theory tables in the SAME
transaction so a partial run never loses data.

The coding tables must already exist — start the server once (TheoryStore creates
them) or run this after import of the app. This script creates them defensively
via TheoryStore if missing.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/split_coding_tags.py
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "kp_mappings.db"
DB = Path(os.environ.get("KP_MAPPING_DB", str(DEFAULT_DB)))

PAIRS = [
    ("theory_question_tags", "coding_question_tags", True),   # has UNIQUE(row_key)
    ("theory_tag_history", "coding_tag_history", False),      # no unique key
]


def _ensure_coding_tables() -> None:
    """Create coding tables if a server boot hasn't already."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from kp_mapping.theory.store import TheoryStore  # noqa: E402

    TheoryStore(DB, tags_table="coding_question_tags", history_table="coding_tag_history")


def _shared_columns(conn: sqlite3.Connection, src: str, dst: str) -> list[str]:
    def cols(t: str) -> list[str]:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]

    src_cols = cols(src)
    dst_cols = set(cols(dst))
    # 'id' is autoincrement on both — never copy it.
    return [c for c in src_cols if c in dst_cols and c != "id"]


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")
    _ensure_coding_tables()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        total_moved = {}
        for src, dst, has_unique in PAIRS:
            cols = _shared_columns(conn, src, dst)
            col_sql = ", ".join(cols)
            verb = "INSERT OR IGNORE" if has_unique else "INSERT"

            src_count = conn.execute(
                f"SELECT COUNT(*) FROM {src} WHERE UPPER(COALESCE(question_type,''))='CODING'"
            ).fetchone()[0]

            # For history (no unique key), only copy when dst is empty to avoid
            # duplicating on re-run.
            if not has_unique:
                dst_existing = conn.execute(f"SELECT COUNT(*) FROM {dst}").fetchone()[0]
                if dst_existing > 0 and src_count > 0:
                    print(
                        f"[skip-copy] {dst} already has {dst_existing} rows; "
                        f"not re-copying {src_count} CODING history rows."
                    )
                    copy = False
                else:
                    copy = True
            else:
                copy = True

            with conn:  # transaction
                if copy and src_count > 0:
                    conn.execute(
                        f"{verb} INTO {dst} ({col_sql}) "
                        f"SELECT {col_sql} FROM {src} "
                        f"WHERE UPPER(COALESCE(question_type,''))='CODING'"
                    )
                # Delete originals regardless (copy already done or skipped because
                # dst already holds them).
                deleted = conn.execute(
                    f"DELETE FROM {src} WHERE UPPER(COALESCE(question_type,''))='CODING'"
                ).rowcount

            dst_count = conn.execute(f"SELECT COUNT(*) FROM {dst}").fetchone()[0]
            total_moved[dst] = dst_count
            print(
                f"{src} -> {dst}: src CODING was {src_count}, "
                f"deleted {deleted} from src, {dst} now {dst_count}"
            )

        # Sanity
        for t in ("theory_question_tags", "theory_tag_history"):
            remaining = conn.execute(
                f"SELECT COUNT(*) FROM {t} WHERE UPPER(COALESCE(question_type,''))='CODING'"
            ).fetchone()[0]
            print(f"remaining CODING in {t}: {remaining}")
        print("done:", total_moved)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
