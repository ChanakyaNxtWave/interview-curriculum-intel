#!/usr/bin/env python3
"""
Tag curriculum coding questions with KPs based on their stored solution code.

Walks curriculum/<course>/**/_coding.json, loads each via the existing
content_loader (which already pulls codes[default_code=true].code_content),
calls the coding-tailored LLM mapper, and upserts the result into the
existing MappingStore (content_mappings table).

Examples:
  # Dry-run: list discovered coding questions
  python scripts/tag_coding_questions.py --dry-run

  # Tag all ProgrammingFoundations coding questions
  python scripts/tag_coding_questions.py

  # Tag only items not yet present in MappingStore (skip everything already tagged)
  python scripts/tag_coding_questions.py --only-untagged

  # Tag a single question by content_id
  python scripts/tag_coding_questions.py --content-id <uuid>

  # Limit / offset (useful for batched runs)
  python scripts/tag_coding_questions.py --limit 25
  python scripts/tag_coding_questions.py --offset 50 --limit 25
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

from kp_mapping.coding_mapper import map_coding_to_kps  # noqa: E402
from kp_mapping.content_loader import discover_content  # noqa: E402
from kp_mapping.kp_catalog import load_catalog  # noqa: E402
from kp_mapping.models import ReviewStatus  # noqa: E402
from kp_mapping.store import MappingStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tag curriculum coding questions with KPs (solution-code-driven)."
    )
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
    parser.add_argument("--limit", type=int, default=0, help="Max items to process (0=all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N items")
    parser.add_argument("--dry-run", action="store_true", help="List content only, no LLM")
    parser.add_argument("--content-id", help="Tag a single content_id only")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between LLM calls")
    parser.add_argument("--model", help="OpenRouter model override")
    parser.add_argument(
        "--only-untagged",
        action="store_true",
        help=(
            "Skip every content_id already present in MappingStore (any "
            "review_status). Only process questions that have never been tagged."
        ),
    )
    args = parser.parse_args()

    if not args.kp_json.exists():
        print(f"KP catalog not found: {args.kp_json}")
        sys.exit(1)

    catalog = load_catalog(args.kp_json)

    pieces = discover_content(
        args.curriculum,
        course_subdir=args.course,
        content_types={"coding_question"},
    )

    if args.content_id:
        pieces = [p for p in pieces if p.content_id == args.content_id]
        if not pieces:
            print(f"No coding question found for content_id {args.content_id}")
            sys.exit(1)

    store = MappingStore(args.db)
    review_map: dict[str, ReviewStatus] = {}
    if args.only_untagged:
        review_map = store.get_review_status_map(content_type="coding_question")
        tagged_ids = set(review_map.keys())
        before = len(pieces)
        pieces = [p for p in pieces if p.content_id not in tagged_ids]
        skipped = before - len(pieces)
        print(
            f"Only untagged: {len(pieces)} to process, {skipped} already tagged (skipped)"
        )

    pieces = pieces[args.offset :]
    if args.limit:
        pieces = pieces[: args.limit]

    print(f"Catalog: {catalog.count} KPs from {args.kp_json.name}")
    print(f"Coding questions to process: {len(pieces)}")

    if args.dry_run:
        # Populate review_map for dry-run labels even if --only-untagged not set.
        if not review_map:
            review_map = store.get_review_status_map(content_type="coding_question")
        for p in pieces:
            sol = "yes" if p.solution_text else ("MISSING" if p.solution_missing else "n/a")
            status = review_map.get(p.content_id)
            status_label = status.value if status else "never_tagged"
            print(
                f"  {p.content_id} | {p.title[:60]} | "
                f"review={status_label} | solution={sol}"
            )
        return

    ok = 0
    flagged = 0
    no_solution = 0
    skipped_empty = 0

    for i, piece in enumerate(pieces, 1):
        print(f"[{i}/{len(pieces)}] {piece.title[:60]}...", flush=True)
        if piece.solution_missing or not piece.solution_text:
            no_solution += 1
            print("    -> SKIP: solution missing/ambiguous")
            continue
        result = map_coding_to_kps(piece, catalog, model=args.model)
        if not result.proposed_tags:
            # Don't upsert empty-tag rows — most commonly an LLM/transport
            # failure (e.g. OpenRouter 403). Leaving the row untagged lets
            # --only-untagged retry on the next run.
            skipped_empty += 1
            reason = "; ".join(result.review_reasons) or "no tags returned"
            print(f"    -> SKIP UPSERT: 0 KPs ({reason})")
            if i < len(pieces) and args.delay:
                time.sleep(args.delay)
            continue
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
        elif result.overall_confidence.value == "high":
            # Auto-approve high-confidence coding mappings that the LLM did
            # not flag — they're immediately retrievable as citations by the
            # interview-question coverage judge. Reviewer can still demote
            # later via PUT /api/mappings/{id}.
            existing = store.get_by_content_id(piece.content_id)
            human_tags = existing.human_tags if existing else []
            store.update_human_review(
                piece.content_id,
                human_tags=human_tags,
                review_status=ReviewStatus.APPROVED,
                reviewer_notes="auto-approved (high conf, no review flag)",
            )
        ok += 1
        kp_ids = ", ".join(t.source_kp_id for t in result.proposed_tags)
        model_info = f", model={result.model}" if result.model else ""
        print(
            f"    -> {len(result.proposed_tags)} KPs [{kp_ids}], "
            f"conf={result.overall_confidence.value}, "
            f"review={result.needs_human_review}{model_info}"
        )
        if i < len(pieces) and args.delay:
            time.sleep(args.delay)

    stats = store.stats()
    print(
        f"\nDone. Processed {ok}, flagged {flagged}, "
        f"no_solution {no_solution}, skipped_empty {skipped_empty}"
    )
    print(f"DB: {args.db}")
    print(f"Stats: {stats}")


if __name__ == "__main__":
    main()
