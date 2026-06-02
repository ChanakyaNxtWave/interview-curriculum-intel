from __future__ import annotations

import json
import os
from typing import Any, Callable

import dspy

from ..kp_catalog import catalog_prompt_block, KPCatalog


_LM_CONFIGURED = False


def configure_lm() -> None:
    """Configure DSPy global LM once (Sonnet via OpenRouter through litellm)."""
    global _LM_CONFIGURED
    if _LM_CONFIGURED:
        return
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY missing — required for DSPy theory pipeline."
        )
    model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
    lm = dspy.LM(
        model=f"openrouter/{model}",
        api_key=api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
        max_tokens=12000,
    )
    dspy.configure(lm=lm)
    _LM_CONFIGURED = True


class IdentifyKPs(dspy.Signature):
    """Pick KPs from the catalog needed to answer the interview question.

    Only use source_kp_id values that appear in kp_catalog. Never invent IDs.
    Confidence values must be one of: high, medium, low, uncertain.
    """

    question: str = dspy.InputField(desc="Interview question text")
    kp_catalog: str = dspy.InputField(desc="List of available KPs: id | label | description")
    required_kps_json: str = dspy.OutputField(
        desc=(
            'JSON array of objects: '
            '[{"source_kp_id": "KP_GLOBAL_0001", "confidence": "high", '
            '"rationale": "..."}]'
        )
    )


class JudgeCoverage(dspy.Signature):
    """Decide whether delivered curriculum content can answer the question.

    HARD RULES — violations are treated as errors by the evaluator:
      • verdict must be exactly one of: covered | not_covered.
        There is no partially_covered, no uncertain — use not_covered for all
        cases where coverage is partial, ambiguous, or absent.
      • overall_confidence ∈ [0,1] measures confidence IN THE CHOSEN VERDICT.
      • Use verdict='covered' ONLY when ≥1 accepted citation from
        candidate_citations_json fully and directly demonstrates the
        technique/concept the question asks about.
        If citations are absent, partial, or tangentially related — use not_covered.
      • If verdict='covered', accepted_citation_ids_json MUST contain ≥1
        content_id from candidate_citations_json.
        If no candidate fully fits, choose not_covered.
      • Use ONLY the provided candidate_citations to support the answer; do not invent.
      • prior_feedback (if non-empty) contains reviewer corrections from previous
        tagging passes on THIS row. Treat it as a hint, not a rule. Override
        feedback when the CURRENT candidate_citations clearly contradict it.
        Specifically: if prior_feedback says "no citations exist / curriculum
        does not cover this" but the current candidate_citations contain
        practice problems whose solutions DO demonstrate the technique, the
        feedback is stale — assess on the actual citations, not on the feedback.
      • question_format='coding': candidate citations are practice problems
        WITH full solutions. tag_role='practice' is normal — coding curriculum has
        no 'explain' role. A practice problem whose solution fully demonstrates
        the same technique the question requires IS valid evidence (covered).
        A partial-overlap match (similar problem, same idiom but not identical)
        is NOT sufficient — use not_covered for partial matches.
        Reject a citation only if the technique itself is absent from its solution.
    """

    question: str = dspy.InputField()
    required_kps_json: str = dspy.InputField()
    candidate_citations_json: str = dspy.InputField()
    prior_feedback: str = dspy.InputField(
        desc="Recent reviewer feedback for this row; empty string if none."
    )
    question_format: str = dspy.InputField(
        desc="theory | coding — affects how to weight tag_role='practice' citations."
    )
    verdict: str = dspy.OutputField(desc="covered | not_covered")
    accepted_citation_ids_json: str = dspy.OutputField(
        desc='JSON array of content_id strings actually used.'
    )
    rationale: str = dspy.OutputField(desc="One paragraph explaining the decision.")
    overall_confidence: str = dspy.OutputField(desc='Numeric string 0..1, e.g. "0.85"')


class AnswerTheoryQuestion(dspy.Signature):
    """Construct an answer to the THEORY interview question using ONLY the
    provided reading-material citation bodies. Do not invent facts.

    HARD RULES:
      • Every factual claim in the answer must be traceable to ≥1 accepted citation.
      • If the citations don't fully support an answer, write what is supported
        and set synthesis_quality='partial'. Do not bluff.
      • If nothing in citations addresses the question, set
        synthesis_quality='insufficient' and write a 1-sentence explanation of
        what's missing from the curriculum.
      • synthesis_quality MUST be exactly one of: complete | partial | insufficient.
      • grounding_json: JSON array mapping each major claim → supporting content_ids.
    """

    question: str = dspy.InputField()
    accepted_citations_json: str = dspy.InputField(
        desc="JSON array of {content_id, title, topic_name, snippet (FULL body)}"
    )
    verdict_hint: str = dspy.InputField(desc="Judge verdict: covered | not_covered")
    synthesized_answer: str = dspy.OutputField(
        desc="Markdown answer derived strictly from citations."
    )
    grounding_json: str = dspy.OutputField(
        desc='JSON array: [{"claim":"...","content_ids":["..."]}]'
    )
    synthesis_quality: str = dspy.OutputField(
        desc="complete | partial | insufficient"
    )
    synthesis_confidence: str = dspy.OutputField(desc='Numeric string 0..1')


class AnswerCodingQuestion(dspy.Signature):
    """Construct an answer to the CODING interview question using the provided
    accepted coding-solution bodies from the curriculum.

    The accepted solutions may be:
      • exact_match — a solution to this exact question (rare),
      • partial_match — solves a sub-problem or shares the key technique,
      • combined — multiple solutions together cover the technique.
    Choose match_strategy accordingly. If no strategy yields a workable answer,
    set synthesis_quality='insufficient' and match_strategy='none'.

    HARD RULES:
      • synthesized_answer MUST contain a Python code block fenced as ```python
        that follows the SAME code pattern / idiom as the cited solutions. Do
        not invent libraries, syntax, or APIs outside what the citations show.
      • Below the code, give a 2–4 sentence walk-through grounded in the citations.
      • Every named technique / function in the answer must appear in ≥1 cited
        solution; grounding_json maps each technique → content_ids.
      • synthesis_quality MUST be exactly one of: complete | partial | insufficient.
      • match_strategy MUST be exactly one of: exact_match | partial_match | combined | none.
    """

    question: str = dspy.InputField()
    accepted_citations_json: str = dspy.InputField(
        desc="JSON array of {content_id, title, topic_name, snippet (FULL solution body)}"
    )
    verdict_hint: str = dspy.InputField(desc="Judge verdict: covered | not_covered")
    synthesized_answer: str = dspy.OutputField(
        desc="Markdown with ```python code``` block followed by explanation."
    )
    grounding_json: str = dspy.OutputField(
        desc='[{"claim":"technique name","content_ids":["..."]}]'
    )
    match_strategy: str = dspy.OutputField(
        desc="exact_match | partial_match | combined | none"
    )
    synthesis_quality: str = dspy.OutputField(
        desc="complete | partial | insufficient"
    )
    synthesis_confidence: str = dspy.OutputField(desc='Numeric string 0..1')


class TheoryPipeline(dspy.Module):
    def __init__(self):
        super().__init__()
        self.identify = dspy.ChainOfThought(IdentifyKPs)
        self.judge = dspy.ChainOfThought(JudgeCoverage)
        self.synth_theory = dspy.ChainOfThought(AnswerTheoryQuestion)
        self.synth_coding = dspy.ChainOfThought(AnswerCodingQuestion)

    def forward(
        self,
        *,
        question: str,
        kp_catalog: str,
        citations_for: Callable[[list[str]], list[dict]],
        prior_feedback: str = "",
        question_format: str = "theory",
    ) -> dspy.Prediction:
        kps_pred = self.identify(question=question, kp_catalog=kp_catalog)
        kp_reasoning = str(getattr(kps_pred, "reasoning", "") or "").strip()
        req_kps = _safe_json_array(kps_pred.required_kps_json)

        req_kps = [
            {
                "source_kp_id": str(item.get("source_kp_id", "")).strip(),
                "confidence": str(item.get("confidence", "uncertain")).lower(),
                "rationale": str(item.get("rationale", "")),
            }
            for item in req_kps
            if isinstance(item, dict) and item.get("source_kp_id")
        ]
        kp_ids = [k["source_kp_id"] for k in req_kps]
        candidates = citations_for(kp_ids) if kp_ids else []

        judge_pred = self.judge(
            question=question,
            required_kps_json=json.dumps(req_kps, ensure_ascii=False),
            candidate_citations_json=json.dumps(
                [
                    {
                        "content_id": c["content_id"],
                        "title": c["title"],
                        "kp_id": c["kp_id"],
                        "tag_role": c["tag_role"],
                        "snippet": c["snippet"],
                    }
                    for c in candidates
                ],
                ensure_ascii=False,
            ),
            prior_feedback=prior_feedback or "",
            question_format=question_format or "theory",
        )
        judge_reasoning = str(getattr(judge_pred, "reasoning", "") or "").strip()
        verdict = _normalize_verdict(judge_pred.verdict)
        accepted_ids = _safe_json_array(judge_pred.accepted_citation_ids_json)
        accepted_ids = [str(x) for x in accepted_ids if isinstance(x, (str, int))]
        conf = _safe_float(judge_pred.overall_confidence)

        accepted_set = set(accepted_ids)
        accepted = [c for c in candidates if c["content_id"] in accepted_set]
        rejected = [c for c in candidates if c["content_id"] not in accepted_set]

        # Stage 3 — AnswerSynthesizer. Fires whenever ≥1 citation was accepted,
        # regardless of judge verdict. The synthesis quality becomes the final
        # authenticity check: complete → covered, insufficient/partial → not_covered.
        synthesized_answer = ""
        grounding: list[Any] = []
        synthesis_quality = "skipped"
        synthesis_confidence = 0.0
        synthesis_reasoning = ""
        match_strategy = ""
        if accepted:
            synth_module = (
                self.synth_coding if question_format == "coding" else self.synth_theory
            )
            accepted_json = json.dumps(
                [
                    {
                        "content_id": c["content_id"],
                        "title": c["title"],
                        "topic_name": c.get("topic_name", ""),
                        "snippet": c["snippet"],
                    }
                    for c in accepted
                ],
                ensure_ascii=False,
            )
            try:
                synth_pred = synth_module(
                    question=question,
                    accepted_citations_json=accepted_json,
                    verdict_hint=verdict,
                )
                synthesized_answer = str(synth_pred.synthesized_answer or "").strip()
                grounding = _safe_json_array(getattr(synth_pred, "grounding_json", ""))
                synthesis_quality = _normalize_quality(
                    getattr(synth_pred, "synthesis_quality", "")
                )
                synthesis_confidence = _safe_float(
                    getattr(synth_pred, "synthesis_confidence", 0.0)
                )
                synthesis_reasoning = str(
                    getattr(synth_pred, "reasoning", "") or ""
                ).strip()
                match_strategy = (
                    str(getattr(synth_pred, "match_strategy", "") or "")
                    .strip()
                    .lower()
                )
            except Exception as exc:
                synthesis_quality = "skipped"
                synthesis_reasoning = f"synthesizer_error: {exc}"

        return dspy.Prediction(
            required_kps=req_kps,
            candidate_citations=candidates,
            accepted_citations=accepted,
            rejected_candidates=rejected,
            verdict=verdict,
            rationale=str(judge_pred.rationale or "").strip(),
            kp_identifier_reasoning=kp_reasoning,
            judge_reasoning=judge_reasoning,
            overall_confidence=conf,
            synthesized_answer=synthesized_answer,
            answer_grounding=grounding,
            synthesis_quality=synthesis_quality,
            synthesis_confidence=synthesis_confidence,
            synthesis_reasoning=synthesis_reasoning,
            match_strategy=match_strategy,
        )


def kp_catalog_prompt(catalog: KPCatalog, *, max_kps: int | None = None) -> str:
    return catalog_prompt_block(catalog, max_kps=max_kps)


def _safe_json_array(raw: str) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw  # type: ignore[return-value]
    text = str(raw).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        val = json.loads(text)
    except (TypeError, ValueError):
        return []
    if isinstance(val, list):
        return val
    return []


def _normalize_quality(v: str) -> str:
    s = (v or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in {"complete", "partial", "insufficient"}:
        return s
    if "complete" in s or "full" in s:
        return "complete"
    if "partial" in s:
        return "partial"
    if "insufficient" in s or "missing" in s or "none" in s:
        return "insufficient"
    return "partial"


def _normalize_verdict(v: str) -> str:
    s = (v or "").strip().lower().replace("-", "_").replace(" ", "_")
    # Collapse old 4-verdict values to binary.
    if s == "covered":
        return "covered"
    if s in {"not_covered", "partially_covered", "uncertain"}:
        return "not_covered"
    if "not" in s and "cover" in s:
        return "not_covered"
    if "partial" in s or "uncertain" in s or "unsure" in s:
        return "not_covered"
    if "cover" in s:
        return "covered"
    return "not_covered"


def _safe_float(v: str | float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f < 0:
        return 0.0
    if f > 1:
        return 1.0
    return f
