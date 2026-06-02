from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from ..content_loader import load_content_file
from ..models import ReviewStatus
from ..store import MappingStore

logger = logging.getLogger("kp_mapping.theory.retrieval")

# Total bytes of combined body text we allow to ship to the judge.
# 60 KB ≈ 15K tokens — well within Sonnet's input window while leaving
# room for question + KP catalog + prior_feedback + fewshot demos.
TOTAL_BODY_BYTES_BUDGET = 60_000


def build_citations_fn(
    mapping_store: MappingStore,
    *,
    per_kp_limit: int = 50,
    total_cap: int = 8,
    content_type: str = "reading_material",
):
    """Return a function (required_kp_ids -> list[citation_dict]) for use by TheoryPipeline.

    Citation snippet contains the FULL body of each content piece (no truncation),
    with title + topic inlined as a header. Total bytes are capped via
    TOTAL_BODY_BYTES_BUDGET to keep judge prompt within model context.

    `content_type` selects which curriculum pieces are eligible:
      • 'reading_material' (default) — for THEORY interview questions.
      • 'coding_question' — for CODING interview questions.
    """
    body_cache: dict[str, str] = {}

    def _body_for(file_path: str) -> str:
        if file_path in body_cache:
            return body_cache[file_path]
        try:
            piece = load_content_file(Path(file_path))
            text = (piece.body_text or "").strip()
        except Exception:
            text = ""
        body_cache[file_path] = text
        return text

    def _build_citation(m, kp_id: str) -> dict:
        tag_role = "explain"
        for t in m.ai_result.proposed_tags:
            if t.source_kp_id == kp_id:
                tag_role = t.tag_role.value
                break
        else:
            for t in m.human_tags:
                if t.source_kp_id == kp_id:
                    tag_role = t.tag_role.value
                    break
        body = _body_for(m.file_path)
        snippet = f"[{m.title}]\n{m.topic_name}\n\n{body}".strip()
        return {
            "content_id": m.content_id,
            "title": m.title,
            "topic_name": m.topic_name,
            "kp_id": kp_id,
            "tag_role": tag_role,
            "snippet": snippet,
            "content_type": m.content_type,
        }

    def citations_for(required_kp_ids: Iterable[str]) -> list[dict]:
        # Pull approved mappings for every required KP, then rank candidates
        # by how many of the required KPs they overlap with. Pieces tagged on
        # multiple required KPs (e.g. "Valid Password - 3" tagged on KPs
        # 0001/0003/0025/0034 — overlap=4 with a 9-KP question) win over
        # narrowly-tagged practice problems that match only one KP. Within
        # same overlap count, prefer the earliest matched KP (preserves the
        # interview's KP order priority).
        required = [k for k in required_kp_ids if k]
        if not required:
            return []
        required_set = set(required)
        kp_priority = {k: i for i, k in enumerate(required)}

        per_content: dict[str, dict] = {}
        for kp_id in required:
            rows = mapping_store.list_mappings(
                kp_id=kp_id,
                review_status=ReviewStatus.APPROVED,
                content_type=content_type,
                limit=per_kp_limit,
            )
            for m in rows:
                if m.content_id not in per_content:
                    per_content[m.content_id] = {
                        "mapping": m,
                        "matched_kps": set(),
                        "first_kp": kp_id,
                    }
                per_content[m.content_id]["matched_kps"].add(kp_id)
                if kp_priority[kp_id] < kp_priority[per_content[m.content_id]["first_kp"]]:
                    per_content[m.content_id]["first_kp"] = kp_id

        # Cross-check: a candidate's full tag set (from ai + human) may overlap
        # additional required KPs beyond the ones whose list_mappings pulled it.
        for content_id, entry in per_content.items():
            m = entry["mapping"]
            tag_kps: set[str] = set()
            for t in getattr(m.ai_result, "proposed_tags", []) or []:
                if t.source_kp_id in required_set:
                    tag_kps.add(t.source_kp_id)
            for t in getattr(m, "human_tags", []) or []:
                if t.source_kp_id in required_set:
                    tag_kps.add(t.source_kp_id)
            entry["matched_kps"].update(tag_kps)
            entry["overlap"] = len(entry["matched_kps"])

        ranked = sorted(
            per_content.values(),
            key=lambda e: (-e["overlap"], kp_priority.get(e["first_kp"], 999)),
        )

        all_candidates: list[dict] = []
        for entry in ranked:
            if len(all_candidates) >= total_cap:
                break
            m = entry["mapping"]
            # Citation's "kp_id" reflects the FIRST required KP this piece
            # matches in the interview's priority order (so the judge sees the
            # most-relevant association).
            all_candidates.append(_build_citation(m, entry["first_kp"]))

        # Then enforce byte budget — drop trailing candidates until under.
        out: list[dict] = []
        used_bytes = 0
        for c in all_candidates:
            cost = len(c["snippet"].encode("utf-8"))
            if used_bytes + cost > TOTAL_BODY_BYTES_BUDGET and out:
                logger.warning(
                    "Citation body budget exceeded (used=%d, cap=%d); dropping %d trailing candidate(s).",
                    used_bytes,
                    TOTAL_BODY_BYTES_BUDGET,
                    len(all_candidates) - len(out),
                )
                break
            out.append(c)
            used_bytes += cost
        return out

    return citations_for


def citation_summary_for_prompt(citations: list[dict]) -> str:
    """Tight string repr of citations for prompts/logs."""
    return json.dumps(
        [
            {
                "content_id": c["content_id"],
                "title": c["title"],
                "kp_id": c["kp_id"],
                "tag_role": c["tag_role"],
                "snippet": c["snippet"],
            }
            for c in citations
        ],
        ensure_ascii=False,
    )
