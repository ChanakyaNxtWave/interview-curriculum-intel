from __future__ import annotations

import logging
import os
from typing import Callable

from ..kp_catalog import KPCatalog
from . import progress as prog
from .compile import load_active_pipeline
from .dspy_modules import kp_catalog_prompt
from .store import TheoryStore

logger = logging.getLogger("kp_mapping.theory.pipeline")


AUTO_APPROVE_CONFIDENCE = float(os.environ.get("THEORY_AUTO_APPROVE_CONF", "0.85"))


def should_auto_approve(verdict: str, confidence: float) -> bool:
    return confidence >= AUTO_APPROVE_CONFIDENCE and verdict != "uncertain"


def derive_can_student_answer(verdict: str, confidence: float) -> bool:
    return verdict in {"covered", "partially_covered"} and confidence >= 0.5


def tag_question(
    *,
    row_key: str,
    question_text: str,
    store: TheoryStore,
    catalog: KPCatalog,
    citations_for: Callable[[list[str]], list[dict]],
    trigger: str = "manual",
) -> dict:
    """Run pipeline on one question, persist tag row, return summary dict.

    Emits per-stage progress to `progress` module so UI can poll.
    """
    prog.start(row_key, trigger=trigger)
    review_reasons: list[str] = []
    prior_feedback = store.latest_feedback_text(row_key)
    if prior_feedback:
        prog.emit(
            row_key,
            "start",
            note=f"inlining {prior_feedback.count(chr(10)) + 1} reviewer feedback item(s)",
        )
    try:
        prog.emit(row_key, "load_active_prompt", note="loading compiled prompt + fewshot demos")
        pipeline, version = load_active_pipeline(store)
        prog.emit(row_key, "load_active_prompt", prompt_version=version or "uninitialized")

        catalog_text = kp_catalog_prompt(catalog)
        # Wrap citations_for so we can capture the candidate stage timing.
        def _retrieve_with_progress(kp_ids: list[str]) -> list[dict]:
            prog.emit(
                row_key,
                "retrieve_citations",
                note=f"retrieving citations for {len(kp_ids)} KP(s)",
            )
            out = citations_for(kp_ids)
            prog.emit(
                row_key,
                "citations_done",
                candidates_count=len(out),
            )
            return out

        prog.emit(row_key, "identify_kps", note="DSPy IdentifyKPs (ChainOfThought)")
        pred = pipeline(
            question=question_text,
            kp_catalog=catalog_text,
            citations_for=_retrieve_with_progress,
            prior_feedback=prior_feedback,
        )
        required_kps = list(pred.required_kps or [])
        candidates = list(pred.candidate_citations or [])
        accepted = list(pred.accepted_citations or [])
        rejected = list(getattr(pred, "rejected_candidates", []) or [])
        verdict = pred.verdict
        rationale = pred.rationale
        confidence = float(pred.overall_confidence)
        kp_reasoning = str(getattr(pred, "kp_identifier_reasoning", "") or "")
        judge_reasoning = str(getattr(pred, "judge_reasoning", "") or "")

        prog.emit(
            row_key,
            "kps_done",
            kps_count=len(required_kps),
        )
        prog.emit(
            row_key,
            "judge_coverage",
            note="DSPy JudgeCoverage (ChainOfThought)",
        )
        prog.emit(
            row_key,
            "judge_done",
            accepted_count=len(accepted),
            verdict=verdict,
            confidence=confidence,
        )
    except Exception as exc:
        logger.exception("Pipeline failed for row_key=%s: %s", row_key, exc)
        required_kps, candidates, accepted, rejected = [], [], [], []
        verdict = "uncertain"
        rationale = ""
        confidence = 0.0
        kp_reasoning = ""
        judge_reasoning = ""
        review_reasons.append(f"pipeline_error: {exc}")
        prog.finish(row_key, error=str(exc))

    if not required_kps:
        review_reasons.append("no_kps_identified")

    # Inverse guard (NEW): model emitted uncertain but is highly confident AND
    # accepted ≥1 citation — that's a contradictory output. Promote to covered
    # before the consistency clamp drops the confidence.
    if verdict == "uncertain" and confidence >= 0.8 and accepted:
        review_reasons.append("auto_promoted_uncertain_to_covered (inconsistent output)")
        verdict = "covered"

    # Consistency clamp (NEW): per signature rule, uncertain must be low confidence.
    # If model violated the rule and we didn't promote, clamp so the row routes to review.
    if verdict == "uncertain" and confidence > 0.5:
        review_reasons.append("uncertain_high_conf_clamped")
        confidence = 0.5

    # Existing forward guard: covered with no accepted citations is invalid.
    if not accepted and verdict in {"covered", "partially_covered"}:
        review_reasons.append("verdict_claims_coverage_without_citations")
        if verdict == "covered":
            verdict = "uncertain"
            confidence = min(confidence, 0.4)

    auto_ok = should_auto_approve(verdict, confidence)
    review_status = "approved" if auto_ok else "needs_review"
    if not auto_ok and "below_auto_approve_threshold" not in review_reasons:
        review_reasons.append(
            f"below_auto_approve_threshold (conf={confidence:.2f}, verdict={verdict})"
        )

    prog.emit(
        row_key,
        "gating",
        note=f"auto_approve={auto_ok} (conf>={AUTO_APPROVE_CONFIDENCE})",
        review_status=review_status,
    )
    prog.emit(row_key, "persisting")

    saved = store.upsert_tag(
        row_key=row_key,
        question_text=question_text,
        required_kps=required_kps,
        citations=accepted,
        candidate_citations=candidates,
        rejected_candidates=rejected,
        verdict=verdict,
        rationale=rationale,
        kp_identifier_reasoning=kp_reasoning,
        judge_reasoning=judge_reasoning,
        overall_confidence=confidence,
        ai_model=os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        prompt_version=locals().get("version") or "uninitialized",
        review_reasons=review_reasons,
        review_status=review_status,
        can_student_answer=derive_can_student_answer(verdict, confidence),
    )
    prog.finish(row_key, result=saved)
    return saved
