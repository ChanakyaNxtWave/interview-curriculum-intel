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

# Exposed in eval dashboard; AI paths do not auto-approve (human review required).
AUTO_APPROVE_CONFIDENCE = 1.0


def _review_status_after_ai(
    store: TheoryStore,
    row_key: str,
    *,
    trigger: str,
) -> str:
    """AI tagging never sets approved — only humans do via the review endpoint."""
    existing = store.get_tag(row_key)
    if not existing:
        return "needs_review"
    prior = (existing.get("review_status") or "").strip()
    if prior in ("rejected", "approved"):
        return prior
    if existing.get("human_verdict"):
        return prior or "needs_review"
    if trigger == "re-tag" and prior in ("pending", "needs_review"):
        return prior
    return "needs_review"


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
    force_human_review: bool = False,
) -> dict:
    """Run pipeline on one question, persist tag row, return summary dict.

    Emits per-stage progress to `progress` module so UI can poll.
    """
    prog.start(row_key, trigger=trigger)
    review_reasons: list[str] = []
    row_feedback = store.latest_feedback_text(row_key)
    global_feedback = store.global_feedback_patterns(limit=20)
    feedback_context_parts = [p for p in (row_feedback, global_feedback) if p]
    prior_feedback = "\n".join(feedback_context_parts)
    if row_feedback:
        prog.emit(
            row_key,
            "start",
            note=f"inlining {row_feedback.count(chr(10)) + 1} reviewer feedback item(s)",
        )
    try:
        prog.emit(row_key, "load_active_prompt", note="loading compiled prompt + fewshot demos")
        pipeline, version = load_active_pipeline(store)
        prog.emit(row_key, "load_active_prompt", prompt_version=version or "uninitialized")

        catalog_text = kp_catalog_prompt(catalog)
        # Wrap citations_for so we can capture the candidate stage timing.
        def _retrieve_with_progress(kp_ids: list[str]) -> list[dict]:
            note = f"retrieving citations for {len(kp_ids)} KP(s)"
            meta_before = getattr(citations_for, "last_meta", None) or {}
            if meta_before.get("retrieval_strategy"):
                note += (
                    f"; strategy={meta_before.get('retrieval_strategy')}"
                )
            prog.emit(row_key, "retrieve_citations", note=note)
            out = citations_for(kp_ids)
            meta = getattr(citations_for, "last_meta", None) or {}
            prog.emit(
                row_key,
                "citations_done",
                candidates_count=len(out),
                kg_tiers=meta.get("tiers_processed"),
                kg_pool_size=meta.get("pool_size"),
                kg_stop_reason=meta.get("stop_reason"),
                kg_retrieval_strategy=meta.get("retrieval_strategy"),
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
        synthesis_quality = "insufficient"
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
    synth_failed = synthesis_quality in {"insufficient", "partial"}
    if synthesis_quality not in {"complete", "partial", "insufficient"}:
        review_reasons.append(f"invalid_synthesis_quality:{synthesis_quality}")
        synthesis_quality = "insufficient"
        synth_failed = True
    if not synthesized_answer.strip():
        review_reasons.append("missing_synthesized_answer")
        synth_failed = True
    if force_human_review:
        review_reasons.append("forced_human_gate_for_changed_row")
    review_status = _review_status_after_ai(store, row_key, trigger=trigger)
    review_reasons.append("awaiting_human_approval")

    prog.emit(
        row_key,
        "gating",
        note="human review required (AI never auto-approves)",
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
