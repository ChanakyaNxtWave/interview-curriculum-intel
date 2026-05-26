from __future__ import annotations

import json
from typing import Any

from .content_loader import ContentPiece
from .kp_catalog import KPCatalog, catalog_prompt_block, validate_kp_ids
from .models import (
    ConfidenceLevel,
    MappingResult,
    ProposedKPTag,
    TagRole,
)
from .llm_client import LLMError, chat_completion, parse_json_response

PROMPT_VERSION = "kp-map-v1"

SYSTEM_PROMPT = """You map curriculum content to Knowledge Points (KPs) from a fixed catalog.

Rules:
1. Only use source_kp_id values from the provided catalog. Never invent IDs.
2. A content piece may map to multiple KPs when justified.
3. For coding questions and projects: base KP mapping ONLY on the provided official solution code, not on guessing from the problem statement alone.
4. If the solution is missing or ambiguous, set needs_human_review true and return few or zero KP tags.
5. Assign per-tag confidence: high, medium, low, uncertain.
6. Set overall_confidence as the minimum confidence among assigned tags, or uncertain if none.
7. Set needs_human_review true when: no suitable KP, ambiguous solution, weak fit, or any invalid uncertainty.
8. tag_role must be one of: explain, practice, example, assessment, project, syntax, prerequisite.

Return JSON only with this schema:
{
  "proposed_tags": [
    {"source_kp_id": "KP_GLOBAL_0001", "tag_role": "practice", "confidence": "high", "rationale": "..."}
  ],
  "overall_confidence": "high",
  "needs_human_review": false,
  "review_reasons": []
}
"""


def _truncate(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def build_user_prompt(piece: ContentPiece, catalog: KPCatalog) -> str:
    parts = [
        "## Knowledge Point Catalog",
        catalog_prompt_block(catalog),
        "",
        "## Content To Map",
        f"content_id: {piece.content_id}",
        f"content_type: {piece.content_type}",
        f"title: {piece.title}",
        f"topic: {piece.topic_name or 'unknown'}",
        f"course: {piece.course_title or 'unknown'}",
        "",
        "### Body",
        _truncate(piece.body_text or "(empty)"),
    ]

    if piece.content_type in ("coding_question", "project"):
        parts.append("")
        parts.append("### Official Solution (use ONLY this for KP mapping)")
        if piece.solution_missing or not piece.solution_text:
            parts.append("MISSING — do not infer KPs from problem text alone. Flag for human review.")
        else:
            parts.append(f"source: {piece.solution_source}")
            parts.append(_truncate(piece.solution_text, 8000))

    return "\n".join(parts)


def _parse_tag(raw: dict[str, Any], catalog: KPCatalog) -> ProposedKPTag | None:
    kp_id = str(raw.get("source_kp_id", "")).strip()
    if not kp_id:
        return None
    valid, _ = validate_kp_ids(catalog, [kp_id])
    if not valid:
        return None
    kp = next(k for k in catalog.knowledge_points if k.source_kp_id == kp_id)
    try:
        confidence = ConfidenceLevel(str(raw.get("confidence", "uncertain")).lower())
    except ValueError:
        confidence = ConfidenceLevel.UNCERTAIN
    try:
        role = TagRole(str(raw.get("tag_role", "practice")).lower())
    except ValueError:
        role = TagRole.PRACTICE
    return ProposedKPTag(
        source_kp_id=kp_id,
        label=kp.label,
        tag_role=role,
        confidence=confidence,
        rationale=str(raw.get("rationale", "")),
    )


def map_content_to_kps(
    piece: ContentPiece,
    catalog: KPCatalog,
    *,
    model: str | None = None,
) -> MappingResult:
    pre_review: list[str] = []
    if piece.content_type in ("coding_question", "project") and piece.solution_missing:
        pre_review.append("No unambiguous official solution code in content JSON")

    user_prompt = build_user_prompt(piece, catalog)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    used_model = model or ""
    try:
        completion = chat_completion(messages, model=model)
        used_model = completion.model_label
        parsed = parse_json_response(completion.content)
    except (LLMError, json.JSONDecodeError) as exc:
        return MappingResult(
            content_id=piece.content_id,
            proposed_tags=[],
            overall_confidence=ConfidenceLevel.UNCERTAIN,
            needs_human_review=True,
            review_reasons=pre_review + [f"LLM call failed: {exc}"],
            model=used_model,
            prompt_version=PROMPT_VERSION,
        )

    tags: list[ProposedKPTag] = []
    invalid_ids: list[str] = []
    for item in parsed.get("proposed_tags") or []:
        if not isinstance(item, dict):
            continue
        kp_id = str(item.get("source_kp_id", "")).strip()
        valid, inv = validate_kp_ids(catalog, [kp_id])
        if inv:
            invalid_ids.extend(inv)
            continue
        tag = _parse_tag(item, catalog)
        if tag:
            tags.append(tag)

    try:
        overall = ConfidenceLevel(
            str(parsed.get("overall_confidence", "uncertain")).lower()
        )
    except ValueError:
        overall = ConfidenceLevel.UNCERTAIN

    needs_review = bool(parsed.get("needs_human_review", False))
    reasons = [str(r) for r in (parsed.get("review_reasons") or [])]
    if pre_review:
        needs_review = True
        reasons = pre_review + reasons
    if invalid_ids:
        needs_review = True
        reasons.append(f"Model returned unknown KP ids: {', '.join(invalid_ids)}")
    if not tags and piece.content_type in ("coding_question", "project") and not piece.solution_missing:
        needs_review = True
        reasons.append("No KPs mapped despite having a solution")

    if tags:
        order = [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.UNCERTAIN]
        confidences = [t.confidence for t in tags]
        overall = min(confidences, key=lambda c: order.index(c))

    return MappingResult(
        content_id=piece.content_id,
        proposed_tags=tags,
        overall_confidence=overall,
        needs_human_review=needs_review,
        review_reasons=reasons,
        model=used_model,
        prompt_version=PROMPT_VERSION,
    )
