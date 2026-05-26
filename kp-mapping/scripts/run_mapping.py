#!/usr/bin/env python3
"""
Manual KP mapping run — discovers curriculum content and maps to KPs via OpenRouter.

Examples:
  # Convert CSV first (once)
  python scripts/convert_kps_csv_to_json.py

  # Dry-run: list content without calling LLM
  python scripts/run_mapping.py --dry-run

  # Map 5 reading materials (pilot)
  python scripts/run_mapping.py --limit 5 --types reading_material

  # Map all coding questions (uses solution code only)
  python scripts/run_mapping.py --types coding_question

  # Only items not yet approved (includes never-mapped + pending/needs_review/rejected)
  python scripts/run_mapping.py --only-unapproved --types reading_material
  python scripts/run_mapping.py --only-unapproved --types coding_question

  # Preview what --only-unapproved would run
  python scripts/run_mapping.py --only-unapproved --types reading_material --dry-run

  # Start review UI
  python scripts/run_review_ui.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from kp_mapping.env import load_env  # noqa: E402

load_env()

from kp_mapping.content_loader import discover_content  # noqa: E402
from kp_mapping.kp_catalog import load_catalog  # noqa: E402
from kp_mapping.mapper import map_content_to_kps  # noqa: E402
from kp_mapping.models import ReviewStatus  # noqa: E402
from kp_mapping.store import MappingStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI KP mapping on curriculum content")
    parser.add_argument(
        "--curriculum",
        type=Path,
        default=REPO_ROOT / "curriculum",
        help="Curriculum root directory",
    )
    parser.add_argument(
        "--kp-json",
        type=Path,
        default=REPO_ROOT / "curriculum" / "KPs-ProgrammingFoundations.json",
        help="KP catalog JSON path",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "data" / "kp_mappings.db",
        help="SQLite database for mappings",
    )
    parser.add_argument(
        "--course",
        default="ProgrammingFoundations",
        help="Course subdirectory under curriculum/",
    )
    parser.add_argument(
        "--types",
        nargs="*",
        choices=["reading_material", "coding_question", "project", "other"],
        help="Limit content types",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max items to process (0=all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N items")
    parser.add_argument("--dry-run", action="store_true", help="List content only, no LLM")
    parser.add_argument("--content-id", help="Map a single content_id only")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between LLM calls")
    parser.add_argument("--model", help="OpenRouter model override")
    parser.add_argument(
        "--only-unapproved",
        action="store_true",
        help=(
            "Skip items with review_status=approved. Includes never-mapped content "
            "and rows that are pending, needs_review, or rejected."
        ),
    )
    args = parser.parse_args()

    if not args.kp_json.exists():
        print(f"KP catalog not found: {args.kp_json}")
        print("Run: python scripts/convert_kps_csv_to_json.py")
        sys.exit(1)

    catalog = load_catalog(args.kp_json)
    type_set = set(args.types) if args.types else None
    pieces = discover_content(
        args.curriculum,
        course_subdir=args.course,
        content_types=type_set,
    )

    if args.content_id:
        pieces = [p for p in pieces if p.content_id == args.content_id]
        if not pieces:
            print(f"No content found for id {args.content_id}")
            sys.exit(1)

    store = MappingStore(args.db)
    review_map: dict[str, ReviewStatus] = {}
    if args.only_unapproved:
        # One content type filter is enough when --types has a single value
        ctype_filter = args.types[0] if args.types and len(args.types) == 1 else None
        review_map = store.get_review_status_map(content_type=ctype_filter)
        before = len(pieces)
        pieces = [
            p
            for p in pieces
            if review_map.get(p.content_id) != ReviewStatus.APPROVED
        ]
        skipped = before - len(pieces)
        print(
            f"Only unapproved: {len(pieces)} to process, {skipped} approved (skipped)"
        )

    pieces = pieces[args.offset :]
    if args.limit:
        pieces = pieces[: args.limit]

    print(f"Catalog: {catalog.count} KPs from {args.kp_json.name}")
    print(f"Content pieces to process: {len(pieces)}")

    if args.dry_run:
        for p in pieces:
            sol = "yes" if p.solution_text else ("MISSING" if p.solution_missing else "n/a")
            status = review_map.get(p.content_id)
            status_label = status.value if status else "never_mapped"
            print(
                f"  [{p.content_type}] {p.content_id} | {p.title[:50]} | "
                f"review={status_label} | solution={sol}"
            )
        return

    ok = 0
    flagged = 0

    for i, piece in enumerate(pieces, 1):
        print(f"[{i}/{len(pieces)}] {piece.title[:60]}...", flush=True)
        result = map_content_to_kps(piece, catalog, model=args.model)
        store.upsert_mapping(
            content_id=piece.content_id,
            file_path=piece.file_path,
            content_type=piece.content_type,
            title=piece.title,
            topic_name=piece.topic_name,
            course_title=piece.course_title,
            ai_result=result,
        )
        if result.needs_human_review:
            flagged += 1
            existing = store.get_by_content_id(piece.content_id)
            human_tags = existing.human_tags if existing else []
            store.update_human_review(
                piece.content_id,
                human_tags=human_tags,
                review_status=ReviewStatus.NEEDS_REVIEW,
                reviewer_notes="; ".join(result.review_reasons),
            )
        ok += 1
        model_info = f", model={result.model}" if result.model else ""
        print(
            f"    -> {len(result.proposed_tags)} tags, "
            f"confidence={result.overall_confidence}, "
            f"review={result.needs_human_review}{model_info}"
        )
        if i < len(pieces) and args.delay:
            time.sleep(args.delay)

    stats = store.stats()
    print(f"\nDone. Processed {ok}, flagged {flagged}")
    print(f"DB: {args.db}")
    print(f"Stats: {stats}")
    print("Start review UI: python scripts/run_review_ui.py")


if __name__ == "__main__":
    main()
