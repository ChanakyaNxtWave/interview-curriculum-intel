from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..kp_catalog import KPCatalog
from ..interview_store import InterviewStore, resolve_date_range
from .compile import (
    check_compile_trigger,
    compile_and_maybe_activate,
    cold_start_if_needed,
)
from .evals import evaluate_pipeline, golds_to_examples
from .dspy_modules import kp_catalog_prompt
from .pipeline import AUTO_APPROVE_CONFIDENCE, tag_question
from . import progress as prog
from .store import TheoryStore

logger = logging.getLogger("kp_mapping.theory.api")


class TagPendingPayload(BaseModel):
    limit: int = 50


class TagBatchPayload(BaseModel):
    row_keys: list[str] = Field(default_factory=list)


class ReviewPayload(BaseModel):
    human_required_kps: list[dict] = Field(default_factory=list)
    human_citations: list[dict] = Field(default_factory=list)
    human_verdict: str
    review_status: str
    reviewer_notes: str = ""
    gold_rationale: str = ""


class FeedbackPayload(BaseModel):
    feedback_type: str
    feedback_text: str
    severity: str = "medium"
    human_verdict: str | None = None


def build_theory_router(
    *,
    theory_store: TheoryStore,
    interview_store: InterviewStore,
    catalog_provider: Callable[[], KPCatalog],
    citations_for: Callable[[list[str]], list[dict]],
    seed_path: Path,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["theory"])

    # ---------- list / detail ----------

    @router.get("/theory-questions")
    def list_theory_questions(
        verdict: str | None = None,
        review_status: str | None = None,
        q: str | None = None,
        duration: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        company_name: str | None = None,
        role: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ):
        df, dt = resolve_date_range(
            duration=duration, date_from=date_from, date_to=date_to
        )
        items = theory_store.list_tags(
            verdict=verdict,
            review_status=review_status,
            q=q,
            date_from=df,
            date_to=dt,
            company_name=company_name,
            role=role,
            limit=limit,
            offset=offset,
        )
        return {
            "total": sum(theory_store.count_by_status().values()),
            "returned": len(items),
            "items": items,
            "stats": {
                "by_status": theory_store.count_by_status(),
                "by_verdict": theory_store.count_by_verdict(),
            },
            "applied_date_range": {
                "duration": duration,
                "date_from": df,
                "date_to": dt,
            },
        }

    @router.get("/theory/active-context")
    def active_context():
        """Snapshot of what the pipeline currently uses on a (re-)tag run."""
        active = theory_store.get_active_prompt_version()
        gold_total = theory_store.count_evals_since(None)
        feedback_total = 0
        with theory_store._connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute("SELECT COUNT(*) FROM theory_review_feedback").fetchone()
            feedback_total = row[0] if row else 0
            sev_rows = conn.execute(
                "SELECT severity, COUNT(*) AS n FROM theory_review_feedback GROUP BY severity"
            ).fetchall()
        feedback_by_severity = {r["severity"]: r["n"] for r in sev_rows}
        catalog = catalog_provider()
        kp_count = len(getattr(catalog, "knowledge_points", []) or [])
        active_dict = (
            {
                "id": active["id"],
                "version": active["version"],
                "fewshot_count": active["fewshot_count"],
                "gold_count_at_compile": active["gold_count_at_compile"],
                "devset_agreement": active["devset_agreement"],
                "created_at": active["created_at"],
            }
            if active
            else None
        )
        return {
            "active_prompt_version": active_dict,
            "gold_set_total": gold_total,
            "feedback_total": feedback_total,
            "feedback_by_severity": feedback_by_severity,
            "kp_catalog_size": kp_count,
            "auto_approve_threshold": AUTO_APPROVE_CONFIDENCE,
            "model": "anthropic/claude-sonnet-4.5",
        }

    @router.get("/theory-questions/{row_key}/tag-status")
    def tag_status(row_key: str):
        rec = prog.get(row_key)
        if not rec:
            return {"row_key": row_key, "stage": "idle", "completed": False}
        return rec

    @router.get("/theory-questions/pending-count")
    def pending_theory_count_alias():
        """Pending count — duplicated route earlier in registration order so FastAPI
        matches it before the generic /{row_key} pattern."""
        reps = set(interview_store.representative_row_keys(question_type="THEORY"))
        approved = {
            t["row_key"]
            for t in theory_store.list_tags(limit=10000)
            if t.get("review_status") == "approved"
        }
        return {"pending": len(reps - approved), "total_representatives": len(reps)}

    @router.get("/theory-questions/{row_key}")
    def get_theory_question(row_key: str):
        row = theory_store.get_tag(row_key)
        if not row:
            raise HTTPException(404, "tag not found")
        # join interview row
        iq_rows = interview_store.list_questions(limit=1, offset=0)
        # Pull by exact row_key using a small ad-hoc query
        iq = None
        for r in iq_rows:
            if r.get("row_key") == row_key:
                iq = r
                break
        if iq is None:
            # Fallback: direct lookup via search
            for r in interview_store.list_questions(limit=1000):
                if r.get("row_key") == row_key:
                    iq = r
                    break
        row["interview"] = iq
        return row

    # ---------- tag ----------

    @router.post("/theory-questions/{row_key}/tag")
    def tag_one(row_key: str):
        iq = None
        for r in interview_store.list_questions(limit=10000):
            if r.get("row_key") == row_key:
                iq = r
                break
        if iq is None:
            raise HTTPException(404, "interview question not found")
        if (iq.get("question_type") or "").upper() != "THEORY":
            raise HTTPException(400, "row is not THEORY")
        existing = theory_store.get_tag(row_key)
        trigger = "re-tag" if existing else "first-tag"
        saved = tag_question(
            row_key=row_key,
            question_text=iq.get("question") or "",
            store=theory_store,
            catalog=catalog_provider(),
            citations_for=citations_for,
            trigger=trigger,
        )
        return saved

    @router.get("/theory-questions/pending-count")
    def pending_theory_count():
        """Return how many representative THEORY rows still need tagging."""
        reps = set(interview_store.representative_row_keys(question_type="THEORY"))
        approved = {
            t["row_key"]
            for t in theory_store.list_tags(limit=10000)
            if t.get("review_status") == "approved"
        }
        return {"pending": len(reps - approved), "total_representatives": len(reps)}

    @router.post("/theory-questions/tag-batch")
    def tag_batch(payload: TagBatchPayload, background_tasks: BackgroundTasks):
        keys = [k for k in payload.row_keys if k]
        if not keys:
            return {"enqueued": 0}
        # Resolve each key to its group representative (if any)
        all_iq = {r["row_key"]: r for r in interview_store.list_questions(limit=20000)}
        rep_map: dict[str, dict] = {}
        for k in keys:
            iq = all_iq.get(k)
            if not iq:
                continue
            rep_key = iq.get("group_representative_row_key") or k
            rep = all_iq.get(rep_key) or iq
            rep_map[rep["row_key"]] = rep
        targets = [v for v in rep_map.values() if (v.get("question_type") or "").upper() == "THEORY"]
        catalog = catalog_provider()

        def _run() -> None:
            for r in targets:
                try:
                    tag_question(
                        row_key=r["row_key"],
                        question_text=r.get("question") or "",
                        store=theory_store,
                        catalog=catalog,
                        citations_for=citations_for,
                    )
                except Exception as exc:
                    logger.exception("batch tag failed for %s: %s", r.get("row_key"), exc)

        background_tasks.add_task(_run)
        return {"enqueued": len(targets)}

    @router.post("/theory-questions/tag-pending")
    def tag_pending(payload: TagPendingPayload, background_tasks: BackgroundTasks):
        # Only THEORY representative rows that aren't yet approved
        reps = interview_store.representative_row_keys(question_type="THEORY")
        already_tagged_ok = {
            t["row_key"]
            for t in theory_store.list_tags(limit=10000)
            if t.get("review_status") == "approved"
        }
        pending_keys = [k for k in reps if k not in already_tagged_ok][: payload.limit]
        all_iq = {r["row_key"]: r for r in interview_store.list_questions(limit=20000)}
        targets = [all_iq[k] for k in pending_keys if k in all_iq]
        catalog = catalog_provider()

        def _run() -> None:
            for r in targets:
                try:
                    tag_question(
                        row_key=r["row_key"],
                        question_text=r.get("question") or "",
                        store=theory_store,
                        catalog=catalog,
                        citations_for=citations_for,
                    )
                except Exception as exc:
                    logger.exception(
                        "bulk tag failed for %s: %s", r.get("row_key"), exc
                    )

        background_tasks.add_task(_run)
        return {"enqueued": len(targets)}

    # ---------- review ----------

    @router.put("/theory-questions/{row_key}/review")
    def review_theory_question(
        row_key: str,
        payload: ReviewPayload,
        background_tasks: BackgroundTasks,
    ):
        existing = theory_store.get_tag(row_key)
        if not existing:
            raise HTTPException(404, "tag not found")
        if payload.human_verdict not in {
            "covered",
            "partially_covered",
            "not_covered",
            "uncertain",
        }:
            raise HTTPException(400, "invalid verdict")
        if payload.review_status not in {
            "pending",
            "approved",
            "rejected",
            "needs_review",
        }:
            raise HTTPException(400, "invalid review_status")

        updated = theory_store.update_human_review(
            row_key,
            human_required_kps=payload.human_required_kps,
            human_citations=payload.human_citations,
            human_verdict=payload.human_verdict,
            review_status=payload.review_status,
            reviewer_notes=payload.reviewer_notes,
        )

        # Determine source: correction if any field diverges from AI; confirmation otherwise.
        ai_kps = {k.get("source_kp_id") for k in (existing.get("required_kps") or [])}
        hu_kps = {k.get("source_kp_id") for k in payload.human_required_kps}
        ai_cits = {c.get("content_id") for c in (existing.get("citations") or [])}
        hu_cits = {c.get("content_id") for c in payload.human_citations}
        is_correction = (
            payload.human_verdict != existing.get("verdict")
            or ai_kps != hu_kps
            or ai_cits != hu_cits
        )
        source = "reviewer_correction" if is_correction else "reviewer_confirmation"

        if not theory_store.eval_exists_for_row(row_key) or is_correction:
            weight, feedback_ids = theory_store.feedback_weight_for(row_key)
            theory_store.insert_eval(
                row_key=row_key,
                question=existing.get("question_text") or "",
                gold_required_kps=payload.human_required_kps,
                gold_citations=payload.human_citations,
                gold_verdict=payload.human_verdict,
                gold_rationale=payload.gold_rationale or existing.get("rationale") or "",
                source=source,
                is_holdout=_should_holdout(theory_store),
                feedback_weight=weight,
                feedback_ids=feedback_ids,
                added_by="reviewer",
            )

        # Check compile trigger in background
        def _maybe_compile() -> None:
            try:
                result = check_compile_trigger(
                    store=theory_store,
                    catalog=catalog_provider(),
                    citations_for=citations_for,
                )
                if result:
                    logger.info("Auto-compile triggered: %s", result)
            except Exception as exc:
                logger.exception("Auto-compile check failed: %s", exc)

        background_tasks.add_task(_maybe_compile)
        return {"tag": updated, "eval_source": source}

    # ---------- eval / compile ----------

    # ---------- feedback / history / improvement ----------

    @router.post("/theory-questions/{row_key}/feedback")
    def submit_feedback(row_key: str, payload: FeedbackPayload):
        existing = theory_store.get_tag(row_key)
        if not existing:
            raise HTTPException(404, "tag not found")
        valid_types = {
            "wrong_verdict",
            "missing_kp",
            "wrong_kp",
            "missing_citation",
            "wrong_citation",
            "general",
        }
        if payload.feedback_type not in valid_types:
            raise HTTPException(400, f"invalid feedback_type; must be one of {sorted(valid_types)}")
        if payload.severity not in {"low", "medium", "high"}:
            raise HTTPException(400, "severity must be low|medium|high")
        if not payload.feedback_text.strip():
            raise HTTPException(400, "feedback_text required")
        theory_store.insert_feedback(
            row_key=row_key,
            prompt_version=existing.get("prompt_version") or "unknown",
            feedback_type=payload.feedback_type,
            feedback_text=payload.feedback_text.strip(),
            severity=payload.severity,
            ai_verdict_at_time=existing.get("verdict"),
            human_verdict=payload.human_verdict,
            added_by="reviewer",
        )
        return {"feedback": theory_store.list_feedback(row_key)}

    @router.get("/theory-questions/{row_key}/feedback")
    def list_feedback(row_key: str):
        return {"feedback": theory_store.list_feedback(row_key)}

    @router.get("/theory-questions/{row_key}/history")
    def get_history(row_key: str, limit: int = 50):
        return {"items": theory_store.list_tag_history(row_key, limit=limit)}

    @router.get("/theory/improvement-summary")
    def improvement_summary():
        return theory_store.improvement_summary()

    @router.get("/theory/eval-runs")
    def list_eval_runs(limit: int = 50):
        return {"items": theory_store.list_eval_runs(limit=limit)}

    @router.post("/theory/eval-now")
    def eval_now():
        from .compile import load_active_pipeline

        pipeline, version = load_active_pipeline(theory_store)
        if not version:
            raise HTTPException(400, "no active prompt version")
        catalog_text = kp_catalog_prompt(catalog_provider())
        dev_rows = theory_store.list_evals(is_holdout=True) or theory_store.list_evals(
            is_holdout=False
        )
        devset = golds_to_examples(
            dev_rows, kp_catalog_text=catalog_text, citations_for=citations_for
        )
        metrics = evaluate_pipeline(pipeline, devset)
        theory_store.insert_eval_run(
            prompt_version=version,
            model="active",
            trigger="manual",
            total=metrics["total"],
            verdict_agree=metrics["verdict_agree"],
            false_covered=metrics["false_covered"],
            false_not_covered=metrics["false_not_covered"],
            kp_jaccard_avg=metrics["kp_jaccard_avg"],
            avg_confidence=metrics["avg_confidence"],
            agreement_rate=metrics["agreement_rate"],
        )
        return {"version": version, "metrics": metrics, "devset_size": len(dev_rows)}

    @router.post("/theory/recompile")
    def recompile():
        try:
            result = compile_and_maybe_activate(
                store=theory_store,
                catalog=catalog_provider(),
                citations_for=citations_for,
                trigger="manual",
            )
        except Exception as exc:
            raise HTTPException(500, f"compile failed: {exc}") from exc
        return result

    @router.get("/theory/prompt-versions")
    def list_versions():
        return {"items": theory_store.list_prompt_versions()}

    @router.post("/theory/prompt-versions/{version_id}/activate")
    def activate(version_id: int):
        ok = theory_store.activate_version(version_id)
        if not ok:
            raise HTTPException(404, "version not found")
        return {"active": theory_store.get_active_prompt_version()}

    @router.post("/theory/cold-start")
    def cold_start():
        return cold_start_if_needed(
            seed_path=seed_path,
            store=theory_store,
            catalog=catalog_provider(),
            citations_for=citations_for,
        )

    return router


def _should_holdout(store: TheoryStore) -> bool:
    """Every 5th gold becomes holdout."""
    n = store.count_evals_since(None)
    return (n + 1) % 5 == 0
