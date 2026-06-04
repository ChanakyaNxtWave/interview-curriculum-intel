from __future__ import annotations

import logging
from typing import Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .fewshot import maybe_update_fewshot

from ..knowledge_graph import KnowledgeGraphError, load_knowledge_graph
from ..kp_catalog import KPCatalog
from ..theory.store import TheoryStore
from .pipeline import (
    build_expanded_graph_payload,
    collect_uncovered_questions,
    run_expansion,
)
from .store import KgExpansionStore

logger = logging.getLogger("kp_mapping.kg_expansion.api")


class StartExpansionPayload(BaseModel):
    question_limit: int = Field(default=25, ge=1, le=200)
    model: str | None = None


class ExpansionFeedbackPayload(BaseModel):
    row_key: str
    proposed_kp_label: str | None = None
    feedback_type: str  # over_granular | missing_prereq | prereq_dump | wrong_catalog_match | label_quality | approved
    feedback_text: str | None = None
    severity: str = "medium"
    human_verdict: str  # approved | rejected | needs_revision


def register_kg_expansion_routes(
    app: FastAPI,
    *,
    expansion_store: KgExpansionStore,
    theory_store: TheoryStore,
    coding_store: TheoryStore,
    catalog_provider: Callable[[], KPCatalog],
) -> None:
    """Register gap-expansion API routes on the main FastAPI app."""

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/uncovered-questions",
        tags=["knowledge-graph-expansion"],
    )
    def list_uncovered_questions(course_id: str, limit: int = 500):
        items = collect_uncovered_questions(theory_store, coding_store, limit=limit)
        return {
            "course_id": course_id,
            "total": len(items),
            "items": items,
        }

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/expansion/runs",
        tags=["knowledge-graph-expansion"],
    )
    def list_expansion_runs(course_id: str, limit: int = 20):
        return {
            "course_id": course_id,
            "runs": expansion_store.list_runs(course_id, limit=limit),
        }

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/expansion/runs/{run_id}",
        tags=["knowledge-graph-expansion"],
    )
    def get_expansion_run(course_id: str, run_id: int):
        run = expansion_store.get_run(run_id)
        if not run or run.get("course_id") != course_id:
            raise HTTPException(404, "expansion run not found")
        return {
            "run": run,
            "questions": expansion_store.list_questions(run_id),
            "proposed_kps": expansion_store.list_proposed_kps(run_id),
            "proposed_nodes": expansion_store.list_proposed_nodes(run_id),
        }

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/expansion",
        tags=["knowledge-graph-expansion"],
    )
    def get_expansion_view(course_id: str, run_id: int | None = None):
        """Expanded graph + diff for a run (latest completed if run_id omitted)."""
        try:
            baseline = load_knowledge_graph(course_id)
        except KnowledgeGraphError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if baseline is None:
            raise HTTPException(404, "Knowledge graph not found for course")

        run = None
        if run_id is not None:
            run = expansion_store.get_run(run_id)
        else:
            run = expansion_store.get_latest_completed_run(course_id)

        uncovered = collect_uncovered_questions(theory_store, coding_store, limit=500)

        if not run or run.get("status") != "completed":
            return {
                "course_id": course_id,
                "baseline": baseline,
                "expanded": None,
                "run": run,
                "uncovered_questions": {
                    "total": len(uncovered),
                    "items": uncovered[:100],
                },
            }

        expanded = build_expanded_graph_payload(
            baseline, int(run["id"]), expansion_store
        )
        return {
            "course_id": course_id,
            "baseline": baseline,
            "expanded": expanded,
            "run": run,
            "uncovered_questions": {
                "total": len(uncovered),
                "items": uncovered[:100],
            },
        }

    @app.post(
        "/api/courses/{course_id}/knowledge-graph/expansion/runs",
        tags=["knowledge-graph-expansion"],
    )
    def start_expansion_run(
        course_id: str,
        payload: StartExpansionPayload,
        background_tasks: BackgroundTasks,
    ):
        try:
            load_knowledge_graph(course_id)
        except KnowledgeGraphError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        questions = collect_uncovered_questions(
            theory_store,
            coding_store,
            limit=payload.question_limit,
        )
        if not questions:
            raise HTTPException(400, "No uncovered (not_covered) questions to process")

        run = expansion_store.create_run(
            course_id=course_id,
            question_limit=payload.question_limit,
            total_questions=len(questions),
        )
        run_id = int(run["id"])

        def _execute() -> None:
            try:
                catalog = catalog_provider()
                run_expansion(
                    run_id=run_id,
                    course_id=course_id,
                    questions=questions,
                    catalog=catalog,
                    expansion_store=expansion_store,
                    model=payload.model,
                )
            except Exception as exc:
                logger.exception("Expansion run %s failed: %s", run_id, exc)

        background_tasks.add_task(_execute)
        return {
            "enqueued": True,
            "run": run,
            "question_count": len(questions),
        }

    @app.post(
        "/api/courses/{course_id}/knowledge-graph/expansion/purge",
        tags=["knowledge-graph-expansion"],
    )
    def purge_expansion_data(course_id: str):
        """Remove all gap-expansion runs and proposed KPs (prepare for re-run)."""
        counts = expansion_store.purge_all_data()
        return {"course_id": course_id, "purged": counts}

    # ---------- feedback ----------

    @app.post(
        "/api/courses/{course_id}/knowledge-graph/expansion/runs/{run_id}/feedback",
        tags=["knowledge-graph-expansion"],
    )
    def submit_expansion_feedback(
        course_id: str,
        run_id: int,
        payload: ExpansionFeedbackPayload,
        background_tasks: BackgroundTasks,
    ):
        run = expansion_store.get_run(run_id)
        if not run or run.get("course_id") != course_id:
            raise HTTPException(404, "expansion run not found")
        valid_types = {
            "over_granular", "missing_prereq", "prereq_dump",
            "wrong_catalog_match", "label_quality", "approved", "general",
        }
        if payload.feedback_type not in valid_types:
            raise HTTPException(
                400, f"invalid feedback_type; must be one of {sorted(valid_types)}"
            )
        if payload.human_verdict not in {"approved", "rejected", "needs_revision"}:
            raise HTTPException(400, "human_verdict must be approved|rejected|needs_revision")
        if payload.severity not in {"low", "medium", "high"}:
            raise HTTPException(400, "severity must be low|medium|high")

        feedback_id = expansion_store.save_expansion_feedback(
            run_id=run_id,
            row_key=payload.row_key,
            proposed_kp_label=payload.proposed_kp_label,
            feedback_type=payload.feedback_type,
            feedback_text=payload.feedback_text,
            severity=payload.severity,
            human_verdict=payload.human_verdict,
        )

        if payload.human_verdict == "rejected":
            def _maybe_update() -> None:
                try:
                    maybe_update_fewshot(expansion_store)
                except Exception as exc:
                    logger.exception("Fewshot update failed after feedback: %s", exc)
            background_tasks.add_task(_maybe_update)

        return {
            "feedback_id": feedback_id,
            "feedback": expansion_store.list_expansion_feedback(run_id),
        }

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/expansion/runs/{run_id}/feedback",
        tags=["knowledge-graph-expansion"],
    )
    def get_expansion_feedback(course_id: str, run_id: int):
        run = expansion_store.get_run(run_id)
        if not run or run.get("course_id") != course_id:
            raise HTTPException(404, "expansion run not found")
        feedback = expansion_store.list_expansion_feedback(run_id)
        patterns = expansion_store.get_rejection_patterns(limit=20)
        return {
            "run_id": run_id,
            "feedback": feedback,
            "rejection_patterns": patterns,
        }

    @app.get(
        "/api/courses/{course_id}/knowledge-graph/expansion/feedback-summary",
        tags=["knowledge-graph-expansion"],
    )
    def get_expansion_feedback_summary(course_id: str):
        runs = expansion_store.list_runs(course_id, limit=50)
        total_feedback = 0
        total_rejected = 0
        rejection_by_type: dict[str, int] = {}
        for run in runs:
            rid = int(run["id"])
            for fb in expansion_store.list_expansion_feedback(rid):
                total_feedback += 1
                if fb.get("human_verdict") == "rejected":
                    total_rejected += 1
                    ft = fb.get("feedback_type") or "general"
                    rejection_by_type[ft] = rejection_by_type.get(ft, 0) + 1
        return {
            "course_id": course_id,
            "total_feedback": total_feedback,
            "total_rejected": total_rejected,
            "rejection_by_type": rejection_by_type,
            "rejection_rate": round(total_rejected / total_feedback, 4) if total_feedback else 0.0,
        }
