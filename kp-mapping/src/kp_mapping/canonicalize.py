from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .interview_store import InterviewStore
from .llm_client import chat_completion, parse_json_response

logger = logging.getLogger("kp_mapping.canonicalize")

CANONICALIZER_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_COURSE_ID = "programming_foundations"
DEFAULT_SHORTLIST_LIMIT = 40
DEFAULT_PENDING_LIMIT = 200


def _slugify(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:120]


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[_\s]+", (text or "").lower()) if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _shortlist_candidates(
    *,
    question: str,
    candidates: list[dict[str, Any]],
    limit: int = DEFAULT_SHORTLIST_LIMIT,
) -> list[dict[str, Any]]:
    qtok = _tokens(question)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        text = f"{c.get('canonical_question', '')} {c.get('canonical_slug', '')}"
        score = _jaccard(qtok, _tokens(text))
        ranked.append((score, c))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:limit]]


@dataclass
class CanonicalDecision:
    action: str  # existing | new
    canonical_id: int | None
    canonical_question: str
    canonical_slug: str
    confidence: float
    reason: str
    model_label: str | None


def _build_prompt(
    *,
    question: str,
    question_type: str,
    course_id: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    candidate_lines = []
    for c in candidates:
        candidate_lines.append(
            f'- id={c["id"]} | q="{c["canonical_question"]}" | slug={c["canonical_slug"]}'
        )
    candidate_block = "\n".join(candidate_lines) if candidate_lines else "(none)"
    system = (
        "You map interview questions to canonical question groups.\n"
        "If any candidate is semantically equivalent (same intent/expected answer), choose existing.\n"
        "If no equivalent exists, create a new canonical question and slug.\n"
        "Return STRICT JSON only."
    )
    user = (
        f"course_id={course_id}\n"
        f"question_type={question_type}\n"
        f'new_question="{question}"\n\n'
        f"candidates:\n{candidate_block}\n\n"
        "Output JSON schema:\n"
        '{\n'
        '  "action": "existing" | "new",\n'
        '  "canonical_id": number|null,\n'
        '  "canonical_question": string,\n'
        '  "canonical_slug": string,\n'
        '  "confidence": number,\n'
        '  "reason": string\n'
        "}\n"
        "Rules:\n"
        "- action=existing only when truly semantically equivalent.\n"
        "- For action=existing set canonical_id from candidates and keep canonical_question/slug from that candidate.\n"
        "- For action=new generate concise canonical_question and stable snake_case canonical_slug."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _coerce_decision(
    raw: dict[str, Any],
    *,
    candidates_by_id: dict[int, dict[str, Any]],
    model_label: str | None,
) -> CanonicalDecision:
    action = str(raw.get("action") or "").strip().lower()
    if action not in {"existing", "new"}:
        action = "new"
    confidence = float(raw.get("confidence") or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    reason = str(raw.get("reason") or "").strip()

    if action == "existing":
        try:
            cid = int(raw.get("canonical_id"))
        except (TypeError, ValueError):
            cid = None
        cand = candidates_by_id.get(cid or -1)
        if not cand:
            action = "new"
        else:
            return CanonicalDecision(
                action="existing",
                canonical_id=int(cand["id"]),
                canonical_question=str(cand.get("canonical_question") or "").strip(),
                canonical_slug=str(cand.get("canonical_slug") or "").strip(),
                confidence=confidence,
                reason=reason or "matched existing canonical",
                model_label=model_label,
            )

    cquestion = str(raw.get("canonical_question") or "").strip()
    cslug = _slugify(str(raw.get("canonical_slug") or ""))
    if not cquestion:
        cquestion = "Untitled canonical question"
    if not cslug:
        cslug = _slugify(cquestion)
    return CanonicalDecision(
        action="new",
        canonical_id=None,
        canonical_question=cquestion,
        canonical_slug=cslug,
        confidence=confidence,
        reason=reason or "no equivalent canonical found",
        model_label=model_label,
    )


def resolve_group_canonical(
    *,
    store: InterviewStore,
    group_key: str,
    question_text: str,
    question_type: str,
    course_id: str = DEFAULT_COURSE_ID,
    shortlist_limit: int = DEFAULT_SHORTLIST_LIMIT,
    model: str = CANONICALIZER_MODEL,
) -> dict[str, Any]:
    existing = store.get_group_canonical(group_key)
    if existing:
        return {"status": "already_linked", "group_key": group_key, "canonical": existing}

    all_candidates = store.list_canonical_candidates(
        question_type=question_type,
        course_id=course_id,
        limit=1000,
    )
    shortlist = _shortlist_candidates(
        question=question_text, candidates=all_candidates, limit=shortlist_limit
    )
    candidates_by_id = {int(c["id"]): c for c in shortlist if c.get("id") is not None}

    completion = chat_completion(_build_prompt(
        question=question_text,
        question_type=question_type,
        course_id=course_id,
        candidates=shortlist,
    ), model=model)
    parsed = parse_json_response(completion.content)
    decision = _coerce_decision(
        parsed,
        candidates_by_id=candidates_by_id,
        model_label=completion.model_label,
    )

    if decision.action == "existing" and decision.canonical_id is not None:
        canonical_id = decision.canonical_id
    else:
        row = store.upsert_canonical_question(
            canonical_question=decision.canonical_question,
            canonical_slug=decision.canonical_slug,
            question_type=question_type,
            course_id=course_id,
        )
        canonical_id = int(row["id"])

    store.link_group_to_canonical(
        group_key=group_key,
        canonical_id=canonical_id,
        decision_source="llm",
        confidence=decision.confidence,
        model_label=decision.model_label,
        reason=decision.reason,
    )
    linked = store.get_group_canonical(group_key)
    return {
        "status": "linked",
        "group_key": group_key,
        "canonical_id": canonical_id,
        "action": decision.action,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "canonical": linked,
    }


def canonicalize_pending_groups(
    *,
    store: InterviewStore,
    question_type: str | None = None,
    limit: int = DEFAULT_PENDING_LIMIT,
    course_id: str = DEFAULT_COURSE_ID,
    model: str = CANONICALIZER_MODEL,
) -> dict[str, Any]:
    pending = store.list_unlinked_groups(question_type=question_type, limit=limit)
    linked = 0
    failed = 0
    for grp in pending:
        try:
            resolve_group_canonical(
                store=store,
                group_key=str(grp["group_key"]),
                question_text=str(grp.get("question") or ""),
                question_type=str((grp.get("question_type") or "THEORY")).upper(),
                course_id=course_id,
                model=model,
            )
            linked += 1
        except Exception as exc:
            failed += 1
            logger.exception(
                "Canonicalize failed for group_key=%s: %s",
                grp.get("group_key"),
                exc,
            )
    return {"pending": len(pending), "linked": linked, "failed": failed}


def canonicalize_row_keys(
    *,
    store: InterviewStore,
    row_keys: list[str],
    course_id: str = DEFAULT_COURSE_ID,
    model: str = CANONICALIZER_MODEL,
) -> dict[str, Any]:
    if not row_keys:
        return {"row_keys": 0, "linked": 0, "failed": 0}
    rows = store.list_questions(limit=20000)
    by_key = {str(r.get("row_key")): r for r in rows if r.get("row_key")}
    seen_groups: set[str] = set()
    linked = 0
    failed = 0
    for rk in row_keys:
        row = by_key.get(rk)
        if not row:
            continue
        group_key = str(row.get("group_key") or "")
        if not group_key or group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        qtext = str(row.get("question") or "").strip()
        qtype = str(row.get("question_type") or "THEORY").upper()
        if not qtext:
            continue
        try:
            resolve_group_canonical(
                store=store,
                group_key=group_key,
                question_text=qtext,
                question_type=qtype,
                course_id=course_id,
                model=model,
            )
            linked += 1
        except Exception as exc:
            failed += 1
            logger.exception("Canonicalize row_key=%s failed: %s", rk, exc)
    return {"row_keys": len(row_keys), "groups": len(seen_groups), "linked": linked, "failed": failed}

