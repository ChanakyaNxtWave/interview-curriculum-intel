from __future__ import annotations

import json
from typing import Any

from .content_loader import ContentPiece
from .kp_catalog import KPCatalog, catalog_prompt_block, validate_kp_ids
from .llm_client import LLMError, chat_completion, parse_json_response
from .models import (
    ConfidenceLevel,
    MappingResult,
    ProposedKPTag,
    TagRole,
)

PROMPT_VERSION = "coding-kp-v2"

# Pinned model for coding KP tagging — DO NOT fall back to other providers.
# Free/weaker models drop JSON structure on long KP-catalog prompts.
CODING_TAGGER_MODEL = "anthropic/claude-sonnet-4.5"

MAX_KPS = 6
MIN_KPS = 1

# KPs treated as noise when a solution already has more than NOISE_DROP_THRESHOLD
# substantive KPs. They tend to show up in nearly every solution (I/O boilerplate,
# split() for input parsing) without being what the question actually teaches.
NOISE_KP_IDS = ("KP_GLOBAL_0007", "KP_GLOBAL_0029")
NOISE_DROP_THRESHOLD = 3

SYSTEM_PROMPT = """You tag Python coding-question solutions with Knowledge Points (KPs) from a fixed catalog.

You decide KPs from the SOLUTION CODE only. Use the problem statement only as context to disambiguate intent.

Rules:
1. Pick 1-6 KPs from the available catalog ONLY. Never invent KP ids.
2. Tag exactly what the solution code uses: language constructs (loops, conditionals, functions),
   operators, built-ins, data structures (list/dict/tuple/set/string), slicing, negative slicing,
   indexing, comprehensions, I/O, string formatting, etc.
3. Order proposed_tags by relevance — the KP most central to the solution comes first.
   Drop incidental KPs (e.g. `int()` cast is rarely the point of the question).
4. Noise-suppression rule: if the solution would warrant MORE THAN 3 KPs, OMIT the following
   KPs entirely because they are I/O boilerplate, not what the question teaches:
     - KP_GLOBAL_0007 (input handling in python — `input()`, `int()` cast)
     - KP_GLOBAL_0029 (string methods in python — when the only method used is `split()`
       for parsing input; KEEP this KP if the solution also uses join/strip/replace/find/etc.)
   If the solution's total relevant KPs is 3 or fewer, you MAY keep these noise KPs.
5. Set per-tag confidence as one of: high, medium, low, uncertain.
6. tag_role is always "practice" for coding questions.
7. overall_confidence is the minimum confidence across tags, or "uncertain" if no tags.
8. needs_human_review is true only if: solution is empty/ambiguous, no KP from the catalog fits,
   or the solution uses something genuinely outside the catalog.

Return JSON only with this schema:
{
  "proposed_tags": [
    {"source_kp_id": "KP_GLOBAL_0001", "tag_role": "practice", "confidence": "high", "rationale": "solution uses X"}
  ],
  "overall_confidence": "high",
  "needs_human_review": false,
  "review_reasons": []
}
"""


_CONFIDENCE_ORDER = [
    ConfidenceLevel.HIGH,
    ConfidenceLevel.MEDIUM,
    ConfidenceLevel.LOW,
    ConfidenceLevel.UNCERTAIN,
]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def build_user_prompt(piece: ContentPiece, catalog: KPCatalog) -> str:
    parts = [
        "## Knowledge Point Catalog",
        catalog_prompt_block(catalog),
        "",
        "## Coding Question",
        f"content_id: {piece.content_id}",
        f"title: {piece.title}",
        f"topic: {piece.topic_name or 'unknown'}",
        f"course: {piece.course_title or 'unknown'}",
        "",
        "### Problem Statement (context only)",
        _truncate(piece.body_text or "(empty)", 6000),
        "",
        "### Official Solution (PRIMARY SOURCE FOR KP TAGGING)",
    ]
    if piece.solution_missing or not piece.solution_text:
        parts.append("MISSING — return 0 tags and set needs_human_review=true.")
    else:
        parts.append(f"source: {piece.solution_source}")
        parts.append("```python")
        parts.append(_truncate(piece.solution_text, 8000))
        parts.append("```")
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
    return ProposedKPTag(
        source_kp_id=kp_id,
        label=kp.label,
        tag_role=TagRole.PRACTICE,
        confidence=confidence,
        rationale=str(raw.get("rationale", "")),
    )


def _overall_confidence(tags: list[ProposedKPTag]) -> ConfidenceLevel:
    if not tags:
        return ConfidenceLevel.UNCERTAIN
    return min(
        (t.confidence for t in tags),
        key=lambda c: _CONFIDENCE_ORDER.index(c),
    )


def map_coding_to_kps(
    piece: ContentPiece,
    catalog: KPCatalog,
    *,
    model: str | None = None,
) -> MappingResult:
    pre_review: list[str] = []
    if piece.solution_missing:
        pre_review.append("No unambiguous default solution code in JSON")

    user_prompt = build_user_prompt(piece, catalog)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    resolved_model = model or CODING_TAGGER_MODEL
    used_model = resolved_model
    try:
        completion = chat_completion(messages, model=resolved_model)
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

    raw_tags = parsed.get("proposed_tags") or []
    tags: list[ProposedKPTag] = []
    invalid_ids: list[str] = []
    seen_kp_ids: set[str] = set()
    for item in raw_tags:
        if not isinstance(item, dict):
            continue
        kp_id = str(item.get("source_kp_id", "")).strip()
        valid, inv = validate_kp_ids(catalog, [kp_id])
        if inv:
            invalid_ids.extend(inv)
            continue
        if kp_id in seen_kp_ids:
            continue
        tag = _parse_tag(item, catalog)
        if tag:
            tags.append(tag)
            seen_kp_ids.add(kp_id)

    # Noise filter: if LLM emitted >3 tags including I/O boilerplate KPs,
    # drop them. Backstop for rule #4 in SYSTEM_PROMPT.
    dropped_noise: list[str] = []
    if len(tags) > NOISE_DROP_THRESHOLD:
        kept: list[ProposedKPTag] = []
        for t in tags:
            if t.source_kp_id in NOISE_KP_IDS and len(tags) - len(dropped_noise) > NOISE_DROP_THRESHOLD:
                dropped_noise.append(t.source_kp_id)
                continue
            kept.append(t)
        tags = kept

    # Clamp to MAX_KPS — preserve LLM ordering (relevance-first per prompt rule).
    over_cap = max(0, len(tags) - MAX_KPS)
    if over_cap:
        tags = tags[:MAX_KPS]

    needs_review = bool(parsed.get("needs_human_review", False))
    reasons = [str(r) for r in (parsed.get("review_reasons") or [])]
    if pre_review:
        needs_review = True
        reasons = pre_review + reasons
    if invalid_ids:
        needs_review = True
        reasons.append(f"Model returned unknown KP ids: {', '.join(invalid_ids)}")
    if dropped_noise:
        reasons.append(f"Dropped noise KPs (>{NOISE_DROP_THRESHOLD} tags rule): {', '.join(dropped_noise)}")
    if over_cap:
        reasons.append(f"Clamped {over_cap} extra KP(s); kept top {MAX_KPS} by LLM order")
    if not tags and not piece.solution_missing:
        needs_review = True
        reasons.append("No KPs mapped despite having a solution")
    if tags and len(tags) < MIN_KPS:
        needs_review = True
        reasons.append(f"Fewer than {MIN_KPS} KPs mapped")

    overall = _overall_confidence(tags)

    return MappingResult(
        content_id=piece.content_id,
        proposed_tags=tags,
        overall_confidence=overall,
        needs_human_review=needs_review,
        review_reasons=reasons,
        model=used_model,
        prompt_version=PROMPT_VERSION,
    )
