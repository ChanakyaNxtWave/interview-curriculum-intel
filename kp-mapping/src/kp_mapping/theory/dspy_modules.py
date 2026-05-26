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
        max_tokens=4096,
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
      • verdict must be exactly one of: covered | partially_covered | not_covered | uncertain.
      • overall_confidence ∈ [0,1] measures confidence IN THE CHOSEN VERDICT.
      • If verdict='uncertain', overall_confidence MUST be ≤ 0.5.
        'uncertain' means: candidate_citations are inconclusive AND you genuinely
        cannot decide between covered / partially_covered / not_covered.
        It is NOT a synonym for "I am confident the answer is unclear" — that
        situation is partially_covered or not_covered.
      • If verdict='covered', accepted_citation_ids_json MUST contain ≥1
        content_id from candidate_citations_json that directly supports the answer.
        If no candidate fits, choose partially_covered or not_covered instead.
      • If a candidate's title or snippet directly names the topic the question
        asks about (e.g. snippet header mentions "break statement" for a question
        about the break keyword), prefer covered / partially_covered over uncertain.
      • Use ONLY the provided candidate_citations to support the answer; do not invent.
      • prior_feedback (if non-empty) contains reviewer corrections from previous
        tagging passes on THIS row. Treat it as a binding hint — only override
        if the candidate citations clearly contradict the feedback.
    """

    question: str = dspy.InputField()
    required_kps_json: str = dspy.InputField()
    candidate_citations_json: str = dspy.InputField()
    prior_feedback: str = dspy.InputField(
        desc="Recent reviewer feedback for this row; empty string if none."
    )
    verdict: str = dspy.OutputField(desc="covered | partially_covered | not_covered | uncertain")
    accepted_citation_ids_json: str = dspy.OutputField(
        desc='JSON array of content_id strings actually used.'
    )
    rationale: str = dspy.OutputField(desc="One paragraph explaining the decision.")
    overall_confidence: str = dspy.OutputField(desc='Numeric string 0..1, e.g. "0.85"')


class TheoryPipeline(dspy.Module):
    def __init__(self):
        super().__init__()
        self.identify = dspy.ChainOfThought(IdentifyKPs)
        self.judge = dspy.ChainOfThought(JudgeCoverage)

    def forward(
        self,
        *,
        question: str,
        kp_catalog: str,
        citations_for: Callable[[list[str]], list[dict]],
        prior_feedback: str = "",
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
        )
        judge_reasoning = str(getattr(judge_pred, "reasoning", "") or "").strip()
        verdict = _normalize_verdict(judge_pred.verdict)
        accepted_ids = _safe_json_array(judge_pred.accepted_citation_ids_json)
        accepted_ids = [str(x) for x in accepted_ids if isinstance(x, (str, int))]
        conf = _safe_float(judge_pred.overall_confidence)

        accepted_set = set(accepted_ids)
        accepted = [c for c in candidates if c["content_id"] in accepted_set]
        rejected = [c for c in candidates if c["content_id"] not in accepted_set]

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


def _normalize_verdict(v: str) -> str:
    s = (v or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in {"covered", "partially_covered", "not_covered", "uncertain"}:
        return s
    if "partial" in s:
        return "partially_covered"
    if "not" in s and "cover" in s:
        return "not_covered"
    if "uncertain" in s or "unsure" in s:
        return "uncertain"
    if "cover" in s:
        return "covered"
    return "uncertain"


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
