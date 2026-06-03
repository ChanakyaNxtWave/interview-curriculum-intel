from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from ..llm_client import LLMError
from ..theory.store import TheoryStore
from .agent import run_agent
from .graph import KnowledgeGraph, KnowledgeNode, load_node_tagger_graph, _topological_order
from .schemas import QuestionInput
from .store import NodeTaggerStore

logger = logging.getLogger("kp_mapping.node_tagger.pipeline")


def collect_uncovered_questions(
    theory_store: TheoryStore,
    coding_store: TheoryStore,
    *,
    question_type: str | None = None,
    limit: int | None = None,
    skip_processed: bool = True,
    node_tagger_store: NodeTaggerStore | None = None,
) -> list[dict]:
    """Fetch not_covered questions, optionally skipping already-processed ones."""
    items: list[dict] = []
    pairs = []
    if question_type is None or question_type.upper() == "THEORY":
        pairs.append((theory_store, "THEORY"))
    if question_type is None or question_type.upper() == "CODING":
        pairs.append((coding_store, "CODING"))

    for store, qt in pairs:
        rows = store.list_tags(verdict="not_covered", limit=limit or 500, offset=0)
        for r in rows:
            items.append(
                {
                    "row_key": r["row_key"],
                    "question_type": qt,
                    "question_text": r.get("question_text") or "",
                    "verdict": r.get("verdict"),
                    "review_status": r.get("review_status"),
                }
            )

    if skip_processed and node_tagger_store is not None:
        processed = node_tagger_store.get_processed_row_keys()
        before = len(items)
        items = [q for q in items if q["row_key"] not in processed]
        skipped = before - len(items)
        if skipped:
            logger.info("skip_processed: %d already-tagged questions skipped", skipped)

    if limit is not None:
        return items[:limit]
    return items


def load_graph_with_canonical(kg_path: Path, store: NodeTaggerStore) -> KnowledgeGraph:
    """Load baseline KG and merge approved canonical nodes into it.

    Canonical nodes become part of the graph so the LLM sees them in the
    catalog prompts and won't re-propose already-approved concepts.
    """
    kg = load_node_tagger_graph(kg_path)
    canonical = store.list_canonical_nodes()
    if not canonical:
        return kg

    existing_ids = {n.knowledge_node_id for n in kg.nodes}
    extra: list[KnowledgeNode] = []
    for c in canonical:
        if c["knowledge_node_id"] in existing_ids:
            continue
        extra.append(
            KnowledgeNode(
                knowledge_node_id=c["knowledge_node_id"],
                label=c["label"],
                description=c["description"],
                prerequisites=[
                    p for p in (c.get("prerequisites") or [])
                    if p in existing_ids or any(
                        x.knowledge_node_id == p for x in extra
                    )
                ],
                depth_level=int(c.get("depth_level") or 0),
            )
        )

    if extra:
        merged_nodes = kg.nodes + extra
        kg = KnowledgeGraph(merged_nodes)
        logger.info(
            "Merged %d canonical node(s) into KG (total %d)", len(extra), len(kg.nodes)
        )
    return kg


def run_node_tagger(
    *,
    run_id: int,
    course_id: str,
    questions: list[dict],
    kg_path: Path,
    store: NodeTaggerStore,
    model: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Process uncovered questions and persist proposed nodes.

    Each question goes through the 2-phase agent. New nodes are deduplicated
    by normalized label within the run. Canonical (approved) nodes from prior
    runs are included in the graph so the LLM can match them instead of
    re-proposing.
    """
    kg = load_graph_with_canonical(kg_path, store)

    label_to_node_id: dict[str, str] = {}

    store.update_run(run_id, status="running")
    processed = 0
    errors = 0
    new_kp_count = 0
    full_coverage_count = 0
    model_label = ""

    try:
        for q in questions:
            row_key = q["row_key"]
            question_text = q.get("question_text") or ""
            question_type = q.get("question_type") or "THEORY"

            inp = QuestionInput(question=question_text)

            try:
                result = run_agent(inp, kg, model=model)
                model_label = model or ""

                new_nodes_raw = [n.model_dump() for n in result.new_nodes]

                store.save_question_result(
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

                if result.coverage_status == "full":
                    full_coverage_count += 1

                for node in result.new_nodes:
                    normalized = node.label.strip().lower()
                    if normalized not in label_to_node_id:
                        label_to_node_id[normalized] = node.knowledge_node_id

                    store.upsert_proposed_node(
                        run_id=run_id,
                        knowledge_node_id=label_to_node_id[normalized],
                        label=node.label,
                        description=node.description,
                        prerequisites=node.prerequisites,
                        depth_level=node.depth_level,
                        row_key=row_key,
                    )
                    new_kp_count += 1

            except (LLMError, ValueError) as exc:
                errors += 1
                logger.exception("Node tagger failed for %s: %s", row_key, exc)
                store.save_question_result(
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

            processed += 1
            store.update_run(run_id, processed_count=processed)
            if on_progress:
                on_progress(processed, len(questions))

        unique_new = len(label_to_node_id)
        stats = {
            "processed": processed,
            "errors": errors,
            "full_coverage": full_coverage_count,
            "new_kps_proposed": new_kp_count,
            "unique_proposed_nodes": unique_new,
        }
        store.update_run(
            run_id,
            status="completed",
            stats=stats,
            model_label=model_label or None,
            completed=True,
        )
        return stats

    except Exception as exc:
        logger.exception("Node tagger run %s failed: %s", run_id, exc)
        store.update_run(
            run_id,
            status="failed",
            error_message=str(exc),
            processed_count=processed,
        )
        raise


def build_expanded_graph_payload(
    baseline_graph: dict[str, Any],
    run_id: int,
    node_tagger_store: NodeTaggerStore,
) -> dict[str, Any]:
    """Merge proposed nodes from a node_tagger run into the baseline graph."""
    baseline_nodes = list(baseline_graph.get("nodes") or [])
    baseline_edges = list(baseline_graph.get("edges") or [])
    baseline_ids = {n["knowledge_node_id"] for n in baseline_nodes}

    proposed_raw = node_tagger_store.list_proposed_nodes(run_id)
    proposed_enriched = node_tagger_store.enrich_proposed_nodes_with_companies(proposed_raw)
    proposed_enriched = sorted(
        proposed_enriched, key=lambda n: (-n.get("touch_count", 0), n.get("label", ""))
    )

    # Also include approved canonical nodes not already in baseline
    canonical = node_tagger_store.list_canonical_nodes()
    canonical_ids = {c["knowledge_node_id"] for c in canonical}

    proposed_ids = {pn["knowledge_node_id"] for pn in proposed_enriched}
    valid_prereq_ids = baseline_ids | proposed_ids | canonical_ids

    expanded_nodes = list(baseline_nodes)
    expanded_edges = list(baseline_edges)
    added_nodes: list[dict[str, Any]] = []

    max_depth = int((baseline_graph.get("stats") or {}).get("max_depth") or 0)

    for pn in proposed_enriched:
        nid = pn["knowledge_node_id"]
        if nid in baseline_ids:
            continue
        prereqs = [
            p for p in (pn.get("prerequisites") or [])
            if p in valid_prereq_ids and p != nid
        ]
        depth = int(pn.get("depth_level") or 0)
        max_depth = max(max_depth, depth)

        entry: dict[str, Any] = {
            "knowledge_node_id": nid,
            "label": pn.get("label", ""),
            "description": pn.get("description", ""),
            "prerequisites": prereqs,
            "depth_level": depth,
            "origin": "proposed",
            "touch_count": pn.get("touch_count", 0),
            "companies": pn.get("companies", []),
            "approval_status": pn.get("approval_status", "pending"),
            "run_id": run_id,
        }
        expanded_nodes.append(entry)
        added_nodes.append(
            {
                "knowledge_node_id": nid,
                "label": entry["label"],
                "touch_count": entry["touch_count"],
                "companies": entry["companies"],
                "approval_status": entry["approval_status"],
            }
        )
        for prereq in prereqs:
            expanded_edges.append({"source": prereq, "target": nid})

    depth_counts = dict((baseline_graph.get("stats") or {}).get("depth_counts") or {})
    for n in expanded_nodes:
        if n.get("origin") == "proposed":
            key = str(n.get("depth_level", 0))
            depth_counts[key] = depth_counts.get(key, 0) + 1

    return {
        **baseline_graph,
        "nodes": expanded_nodes,
        "edges": expanded_edges,
        "stats": {
            **(baseline_graph.get("stats") or {}),
            "node_count": len(expanded_nodes),
            "edge_count": len(expanded_edges),
            "max_depth": max_depth,
            "depth_counts": depth_counts,
            "proposed_node_count": len(added_nodes),
        },
        "expansion": {
            "run_id": run_id,
            "proposed_nodes": proposed_enriched,
            "diff": {
                "baseline_node_count": len(baseline_nodes),
                "expanded_node_count": len(expanded_nodes),
                "added_node_count": len(added_nodes),
                "added_nodes": added_nodes,
            },
        },
    }
