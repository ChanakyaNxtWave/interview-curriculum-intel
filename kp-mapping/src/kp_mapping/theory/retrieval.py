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
    per_kp_limit: int = 5,
    total_cap: int = 8,
):
    """Return a function (required_kp_ids -> list[citation_dict]) for use by TheoryPipeline.

    Citation snippet contains the FULL body of each content piece (no truncation),
    with title + topic inlined as a header. Total bytes are capped via
    TOTAL_BODY_BYTES_BUDGET to keep judge prompt within model context.
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

    def citations_for(required_kp_ids: Iterable[str]) -> list[dict]:
        # Collect candidates ordered: reading_material first, then others.
        all_candidates: list[dict] = []
        seen: set[str] = set()
        for kp_id in required_kp_ids:
            if not kp_id:
                continue
            rows = mapping_store.list_mappings(
                kp_id=kp_id,
                review_status=ReviewStatus.APPROVED,
                content_type="reading_material",
                limit=per_kp_limit,
            )
            for m in rows:
                if m.content_id in seen:
                    continue
                seen.add(m.content_id)
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
                all_candidates.append(
                    {
                        "content_id": m.content_id,
                        "title": m.title,
                        "topic_name": m.topic_name,
                        "kp_id": kp_id,
                        "tag_role": tag_role,
                        "snippet": snippet,
                        "content_type": m.content_type,
                    }
                )

        # Enforce total_cap first
        all_candidates = all_candidates[:total_cap]

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
