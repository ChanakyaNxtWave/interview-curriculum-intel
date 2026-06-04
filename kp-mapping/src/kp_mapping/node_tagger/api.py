from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..kg_expansion.store import KgExpansionStore
from ..knowledge_graph import KnowledgeGraphError, load_knowledge_graph, load_knowledge_graph_raw
from ..theory.store import TheoryStore
from .pipeline import (
    build_expanded_graph_payload,
    collect_uncovered_questions,
    run_node_tagger,
)
from .store import NodeTaggerStore

logger = logging.getLogger("kp_mapping.node_tagger.api")

_REJECTION_REASON_TO_FEEDBACK_TYPE = {
    "too_granular": "over_granular",
    "duplicate": "label_quality",
    "out_of_scope": "label_quality",
    "wrong_level": "missing_prereq",
    "other": "general",
}


class StartNodeTaggerPayload(BaseModel):
    question_limit: int = Field(default=25, ge=1, le=200)
    question_type: str | None = None  # "THEORY" | "CODING" | None (both)
    model: str | None = None
    skip_processed: bool = True


class ApprovalPayload(BaseModel):
    approval_status: Literal["approved", "rejected"]
    rejection_reason: Literal["too_granular", "duplicate", "out_of_scope", "wrong_level", "other"] | None = None
    notes: str | None = None


def _build_node_label_map(kg_path: Path) -> dict[str, str]:
    """Return {knowledge_node_id: label} for the baseline graph."""
    try:
        raw = load_knowledge_graph_raw(kg_path.stem.replace("programming_foundations_knowledge_nodes", "programming_foundations"))
        if raw is None:
            return {}
        return {n["knowledge_node_id"]: n.get("label", "") for n in raw.get("nodes") or []}
    except Exception:
        return {}


def _label_map_from_path(kg_path: Path) -> dict[str, str]:
    """Load {uuid: label} directly from the JSON file (no course_slug needed)."""
    import json
    try:
        data = json.loads(kg_path.read_text(encoding="utf-8"))
        nodes = data.get("knowledge_nodes") or (data if isinstance(data, list) else [])
        return {n["knowledge_node_id"]: n.get("label", "") for n in nodes}
    except Exception:
        return {}


def register_node_tagger_routes(
    app: FastAPI,
    *,
    node_tagger_store: NodeTaggerStore,
    theory_store: TheoryStore,
    coding_store: TheoryStore,
    kg_path_provider: Callable[[], Path],
    expansion_store: KgExpansionStore | None = None,
) -> None:
    """Register node-tagger API routes on the main FastAPI app."""

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/uncovered-questions",
        tags=["node-tagger"],
    )
    def list_uncovered_questions_nt(
        course_id: str, limit: int = 500, skip_processed: bool = False
    ):
        items = collect_uncovered_questions(
            theory_store,
            coding_store,
            limit=limit,
            skip_processed=skip_processed,
            node_tagger_store=node_tagger_store if skip_processed else None,
        )
        processed_count = len(node_tagger_store.get_processed_row_keys())
        return {
            "course_id": course_id,
            "total": len(items),
            "total_processed": processed_count,
            "items": items,
        }

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/runs",
        tags=["node-tagger"],
    )
    def list_node_tagger_runs(course_id: str, limit: int = 20):
        return {
            "course_id": course_id,
            "runs": node_tagger_store.list_runs(course_id, limit=limit),
        }

    @app.post(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/runs",
        tags=["node-tagger"],
    )
    def start_node_tagger_run(
        course_id: str,
        payload: StartNodeTaggerPayload,
        background_tasks: BackgroundTasks,
    ):
        try:
            load_knowledge_graph(course_id)
        except KnowledgeGraphError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        questions = collect_uncovered_questions(
            theory_store,
            coding_store,
            question_type=payload.question_type,
            limit=payload.question_limit,
            skip_processed=payload.skip_processed,
            node_tagger_store=node_tagger_store if payload.skip_processed else None,
        )
        if not questions:
            raise HTTPException(
                400,
                "No unprocessed not_covered questions to process. "
                "All questions may already be tagged. Use skip_processed=false to reprocess.",
            )

        run = node_tagger_store.create_run(
            course_id=course_id,
            question_limit=payload.question_limit,
            total_questions=len(questions),
        )
        run_id = int(run["id"])
        kg_path = kg_path_provider()

        def _execute() -> None:
            try:
                run_node_tagger(
                    run_id=run_id,
                    course_id=course_id,
                    questions=questions,
                    kg_path=kg_path,
                    store=node_tagger_store,
                    model=payload.model,
                )
            except Exception as exc:
                logger.exception("Node tagger run %s failed: %s", run_id, exc)

        background_tasks.add_task(_execute)
        return {"enqueued": True, "run": run, "question_count": len(questions)}

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/runs/{run_id}",
        tags=["node-tagger"],
    )
    def get_node_tagger_run(course_id: str, run_id: int):
        run = node_tagger_store.get_run(run_id)
        if not run or run.get("course_id") != course_id:
            raise HTTPException(404, "node tagger run not found")

        proposed = node_tagger_store.list_proposed_nodes(run_id)
        proposed = node_tagger_store.enrich_proposed_nodes_with_companies(proposed)
        proposed = sorted(
            proposed, key=lambda n: (-n.get("touch_count", 0), n.get("label", ""))
        )

        # Enrich questions with resolved node labels
        questions = node_tagger_store.list_questions(run_id)
        label_map = _label_map_from_path(kg_path_provider())
        # Also add proposed node labels to the label map
        for pn in proposed:
            label_map.setdefault(pn["knowledge_node_id"], pn.get("label", ""))

        for q in questions:
            q["existing_node_labels"] = [
                label_map.get(nid, nid) for nid in (q.get("existing_node_ids") or [])
            ]
            q["new_node_labels"] = [
                n.get("label", "") for n in (q.get("new_nodes") or [])
            ]

        # Build question text lookup for proposed nodes (so UI can show which questions need each KP)
        rk_to_question: dict[str, dict] = {q["row_key"]: q for q in questions}
        for pn in proposed:
            pn["question_previews"] = [
                {
                    "row_key": rk,
                    "question_type": rk_to_question[rk]["question_type"] if rk in rk_to_question else "",
                    "question_text": (rk_to_question[rk]["question_text"] if rk in rk_to_question else rk)[:120],
                }
                for rk in (pn.get("question_row_keys") or [])
            ]

        return {
            "run": run,
            "questions": questions,
            "proposed_nodes": proposed,
        }

    @app.patch(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/runs/{run_id}/nodes/{knowledge_node_id}",
        tags=["node-tagger"],
    )
    def set_node_approval(
        course_id: str, run_id: int, knowledge_node_id: str, payload: ApprovalPayload
    ):
        """Approve or reject a proposed KP node. Approved → saved to canonical_nodes.
        Rejected → rejection_reason stored; wired to KG expansion feedback if expansion_store available.
        """
        run = node_tagger_store.get_run(run_id)
        if not run or run.get("course_id") != course_id:
            raise HTTPException(404, "run not found")
        updated = node_tagger_store.set_node_approval(
            run_id,
            knowledge_node_id,
            payload.approval_status,
            rejection_reason=payload.rejection_reason,
            rejection_notes=payload.notes,
        )
        if updated is None:
            raise HTTPException(404, "proposed node not found")

        # Wire rejection to KG expansion feedback so it informs future fewshot updates.
        if payload.approval_status == "rejected" and expansion_store is not None:
            latest_kg_run = expansion_store.get_latest_completed_run(course_id)
            if latest_kg_run:
                feedback_type = _REJECTION_REASON_TO_FEEDBACK_TYPE.get(
                    payload.rejection_reason or "other", "general"
                )
                try:
                    expansion_store.save_expansion_feedback(
                        run_id=int(latest_kg_run["id"]),
                        row_key=knowledge_node_id,
                        proposed_kp_label=updated.get("label"),
                        feedback_type=feedback_type,
                        feedback_text=payload.notes,
                        severity="medium",
                        human_verdict="rejected",
                        added_by="node_tagger_reviewer",
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to save node-tagger rejection to expansion feedback: %s", exc
                    )

        return {"node": updated, "canonical_nodes_count": len(node_tagger_store.list_canonical_nodes())}

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/canonical-nodes",
        tags=["node-tagger"],
    )
    def list_canonical_nodes(course_id: str):
        """All approved canonical KP nodes across all runs."""
        nodes = node_tagger_store.list_canonical_nodes()
        return {"course_id": course_id, "total": len(nodes), "nodes": nodes}

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/expansion",
        tags=["node-tagger"],
    )
    def get_node_tagger_expansion(course_id: str, run_id: int | None = None):
        """Expanded graph (baseline + proposed) for a node-tagger run."""
        try:
            baseline = load_knowledge_graph(course_id)
        except KnowledgeGraphError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if baseline is None:
            raise HTTPException(404, "Knowledge graph not found for course")

        run = None
        if run_id is not None:
            run = node_tagger_store.get_run(run_id)
        else:
            run = node_tagger_store.get_latest_completed_run(course_id)

        uncovered = collect_uncovered_questions(theory_store, coding_store, limit=500)
        processed_count = len(node_tagger_store.get_processed_row_keys())

        if not run or run.get("status") != "completed":
            return {
                "course_id": course_id,
                "baseline": baseline,
                "expanded": None,
                "run": run,
                "uncovered_questions": {
                    "total": len(uncovered),
                    "total_processed": processed_count,
                    "items": uncovered[:100],
                },
            }

        expanded = build_expanded_graph_payload(baseline, int(run["id"]), node_tagger_store)
        return {
            "course_id": course_id,
            "baseline": baseline,
            "expanded": expanded,
            "run": run,
            "uncovered_questions": {
                "total": len(uncovered),
                "total_processed": processed_count,
                "items": uncovered[:100],
            },
        }

    @app.post(
        "/api/courses/{course_id}/knowledge-graph/node-tagger/purge",
        tags=["node-tagger"],
    )
    def purge_node_tagger_data(course_id: str):
        counts = node_tagger_store.purge_all_data()
        return {"course_id": course_id, "purged": counts}
