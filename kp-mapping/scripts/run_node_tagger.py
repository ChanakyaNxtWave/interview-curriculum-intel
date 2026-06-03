#!/usr/bin/env python3
"""
Run the node_tagger pipeline on uncovered interview questions.

Examples:
  # Dry-run: list uncovered questions without calling LLM
  python scripts/run_node_tagger.py --dry-run

  # Process all uncovered questions (theory + coding)
  python scripts/run_node_tagger.py

  # Limit to 10 questions
  python scripts/run_node_tagger.py --limit 10

  # Theory questions only
  python scripts/run_node_tagger.py --question-type theory

  # Model override
  python scripts/run_node_tagger.py --model anthropic/claude-sonnet-4-5
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

from kp_mapping.node_tagger.agent import run_agent  # noqa: E402
from kp_mapping.node_tagger.graph import load_node_tagger_graph  # noqa: E402
from kp_mapping.node_tagger.pipeline import collect_uncovered_questions  # noqa: E402
from kp_mapping.node_tagger.schemas import QuestionInput  # noqa: E402
from kp_mapping.node_tagger.store import NodeTaggerStore  # noqa: E402
from kp_mapping.theory.store import TheoryStore  # noqa: E402

DEFAULT_DB = ROOT / "data" / "kp_mappings.db"
DEFAULT_KG_JSON = (
    REPO_ROOT
    / "curriculum"
    / "ProgrammingFoundations"
    / "programming_foundations_knowledge_nodes.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run node_tagger on uncovered interview questions."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--kg-json", type=Path, default=DEFAULT_KG_JSON,
        help="Path to programming_foundations_knowledge_nodes.json"
    )
    parser.add_argument(
        "--question-type",
        choices=["theory", "coding"],
        default=None,
        help="Process only this question type (default: both)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max questions (0=all)")
    parser.add_argument("--model", default=None, help="LLM model override")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between LLM calls")
    parser.add_argument("--dry-run", action="store_true", help="List questions, no LLM")
    args = parser.parse_args()

    if not args.kg_json.exists():
        print(f"Knowledge graph JSON not found: {args.kg_json}")
        sys.exit(1)

    theory_store = TheoryStore(args.db)
    coding_store = TheoryStore(
        args.db,
        tags_table="coding_question_tags",
        history_table="coding_tag_history",
    )
    node_tagger_store = NodeTaggerStore(args.db)

    qt_filter = args.question_type.upper() if args.question_type else None
    limit = args.limit or None

    questions = collect_uncovered_questions(
        theory_store, coding_store, question_type=qt_filter, limit=limit
    )
    print(f"Uncovered questions to process: {len(questions)}")

    if args.dry_run:
        for q in questions:
            print(
                f"  [{q['question_type']}] {q['row_key']} | "
                f"review={q.get('review_status')} | "
                f"{q['question_text'][:80]}..."
            )
        return

    kg = load_node_tagger_graph(args.kg_json)
    print(f"Knowledge graph loaded: {len(kg.nodes)} nodes from {args.kg_json.name}")

    run = node_tagger_store.create_run(
        course_id="programming_foundations",
        question_limit=len(questions),
        total_questions=len(questions),
    )
    run_id = int(run["id"])
    print(f"Run created: id={run_id}")

    label_to_node_id: dict[str, str] = {}

    ok = 0
    errors = 0
    new_kps = 0

    for i, q in enumerate(questions, 1):
        row_key = q["row_key"]
        question_text = q["question_text"]
        question_type = q["question_type"]
        print(f"[{i}/{len(questions)}] [{question_type}] {question_text[:70]}...", flush=True)

        inp = QuestionInput(question=question_text)
        try:
            result = run_agent(inp, kg, model=args.model)
            new_nodes_raw = [n.model_dump() for n in result.new_nodes]
            node_tagger_store.save_question_result(
                run_id=run_id,
                row_key=row_key,
                question_type=question_type,
                question_text=question_text,
                coverage_status=result.coverage_status,
                existing_node_ids=result.existing_node_ids,
                new_nodes=new_nodes_raw,
                reasoning=result.reasoning,
                error_message=None,
            )
            for node in result.new_nodes:
                normalized = node.label.strip().lower()
                if normalized not in label_to_node_id:
                    label_to_node_id[normalized] = node.knowledge_node_id
                node_tagger_store.upsert_proposed_node(
                    run_id=run_id,
                    knowledge_node_id=label_to_node_id[normalized],
                    label=node.label,
                    description=node.description,
                    prerequisites=node.prerequisites,
                    depth_level=node.depth_level,
                    row_key=row_key,
                )
                new_kps += 1

            print(
                f"    -> coverage={result.coverage_status}, "
                f"existing={len(result.existing_node_ids)}, "
                f"new={len(result.new_nodes)}"
            )
            ok += 1
        except Exception as exc:
            errors += 1
            print(f"    -> ERROR: {exc}")
            node_tagger_store.save_question_result(
                run_id=run_id,
                row_key=row_key,
                question_type=question_type,
                question_text=question_text,
                coverage_status=None,
                existing_node_ids=[],
                new_nodes=[],
                reasoning=None,
                error_message=str(exc),
            )

        node_tagger_store.update_run(run_id, processed_count=i)
        if i < len(questions) and args.delay:
            time.sleep(args.delay)

    stats = {
        "processed": ok + errors,
        "errors": errors,
        "new_kps_proposed": new_kps,
        "unique_proposed_nodes": len(label_to_node_id),
    }
    node_tagger_store.update_run(
        run_id,
        status="completed" if not errors else "completed",
        stats=stats,
        model_label=args.model or "",
        completed=True,
    )
    print(f"\nDone. ok={ok}, errors={errors}, new_kps={new_kps}, unique={len(label_to_node_id)}")
    print(f"Run id={run_id} — view via API or node_tagger_store.list_proposed_nodes({run_id})")


if __name__ == "__main__":
    main()
