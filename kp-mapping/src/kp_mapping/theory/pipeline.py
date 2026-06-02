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
    return confidence >= AUTO_APPROVE_CONFIDENCE


def derive_can_student_answer(
    verdict: str, confidence: float, synthesis_quality: str = "skipped"
) -> bool:
    """Real "can a student answer this from curriculum" signal."""
    if synthesis_quality == "complete":
        return True
    if synthesis_quality in {"partial", "insufficient"}:
        return False
    # skipped → heuristic: only covered with sufficient confidence
    return verdict == "covered" and confidence >= 0.5


def tag_question(
    *,
    row_key: str,
    question_text: str,
    store: TheoryStore,
    catalog: KPCatalog,
    citations_for: Callable[[list[str]], list[dict]],
    trigger: str = "manual",
    question_type: str = "THEORY",
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
        question_format = "coding" if (question_type or "").upper() == "CODING" else "theory"
        pred = pipeline(
            question=question_text,
            kp_catalog=catalog_text,
            citations_for=_retrieve_with_progress,
            prior_feedback=prior_feedback,
            question_format=question_format,
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
        synthesized_answer = str(getattr(pred, "synthesized_answer", "") or "")
        answer_grounding = list(getattr(pred, "answer_grounding", []) or [])
        synthesis_quality = str(getattr(pred, "synthesis_quality", "skipped") or "skipped")
        synthesis_confidence = float(getattr(pred, "synthesis_confidence", 0.0) or 0.0)
        synthesis_reasoning = str(getattr(pred, "synthesis_reasoning", "") or "")
        match_strategy = str(getattr(pred, "match_strategy", "") or "")

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
        if synthesis_quality != "skipped":
            prog.emit(
                row_key,
                "synthesize_answer",
                note=(
                    "DSPy AnswerCodingQuestion (CoT)"
                    if question_format == "coding"
                    else "DSPy AnswerTheoryQuestion (CoT)"
                ),
            )
            prog.emit(
                row_key,
                "synthesize_done",
                synthesis_quality=synthesis_quality,
                synthesis_confidence=synthesis_confidence,
                match_strategy=match_strategy,
            )
    except Exception as exc:
        logger.exception("Pipeline failed for row_key=%s: %s", row_key, exc)
        required_kps, candidates, accepted, rejected = [], [], [], []
        verdict = "not_covered"
        rationale = ""
        confidence = 0.0
        kp_reasoning = ""
        judge_reasoning = ""
        synthesized_answer = ""
        answer_grounding = []
        synthesis_quality = "skipped"
        synthesis_confidence = 0.0
        synthesis_reasoning = ""
        match_strategy = ""
        review_reasons.append(f"pipeline_error: {exc}")
        prog.finish(row_key, error=str(exc))

    if not required_kps:
        review_reasons.append("no_kps_identified")

    # Collapse any leaked old verdicts (model output or compiled prompt may still
    # emit partially_covered/uncertain during transition period).
    if verdict in {"partially_covered", "uncertain"}:
        review_reasons.append(f"verdict_collapsed_to_not_covered (was {verdict})")
        verdict = "not_covered"

    # Forward guard: covered with no accepted citations is invalid → not_covered.
    if not accepted and verdict == "covered":
        review_reasons.append("verdict_claims_coverage_without_citations")
        verdict = "not_covered"
        confidence = min(confidence, 0.4)

    # Stage-3 quality gate — synthesizer is the final authenticity check.
    if synthesis_quality in {"insufficient", "partial"} and verdict == "covered":
        # Downgrade: judge said covered but synthesizer couldn't produce an answer.
        review_reasons.append(
            f"synthesis_{synthesis_quality}: curriculum cannot fully answer "
            f"(prior verdict={verdict}, conf={confidence:.2f})"
        )
        verdict = "not_covered"
    elif synthesis_quality == "complete" and verdict == "not_covered" and accepted:
        # Upgrade: judge said not_covered but synthesizer answered fully from citations.
        review_reasons.append("synthesis_complete_upgraded_to_covered")
        verdict = "covered"

    # Hard block: never auto-approve when KP identification failed — judge had
    # no citations to evaluate so its verdict is uninformed.
    pipeline_failed = any(
        r == "no_kps_identified" or r.startswith("pipeline_error")
        for r in review_reasons
    )
    synth_failed = synthesis_quality == "insufficient"
    auto_ok = (
        should_auto_approve(verdict, confidence)
        and not pipeline_failed
        and not synth_failed
    )
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
        can_student_answer=derive_can_student_answer(
            verdict, confidence, synthesis_quality
        ),
        question_type=(question_type or "THEORY").upper(),
        synthesized_answer=synthesized_answer,
        answer_grounding=answer_grounding,
        synthesis_quality=synthesis_quality,
        synthesis_confidence=synthesis_confidence,
        synthesis_reasoning=synthesis_reasoning,
        match_strategy=match_strategy,
    )
    prog.finish(row_key, result=saved)
    return saved
