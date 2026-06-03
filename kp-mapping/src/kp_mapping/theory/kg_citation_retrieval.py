from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Iterable

from ..content_loader import load_content_file
from ..knowledge_graph import load_knowledge_graph
from ..models import ReviewStatus
from ..store import MappingStore
from .retrieval import TOTAL_BODY_BYTES_BUDGET, build_citations_fn

logger = logging.getLogger("kp_mapping.theory.kg_citation_retrieval")

MAX_TIER_PASSES = 4
MIN_POOL_BEFORE_STOP = 10
DEFAULT_COURSE_ID = "programming_foundations"


def depth_by_kp_from_graph(course_id: str) -> dict[str, int]:
    graph = load_knowledge_graph(course_id)
    if not graph:
        return {}
    out: dict[str, int] = {}
    for node in graph.get("nodes") or []:
        sk = node.get("source_kp_id")
        if sk:
            out[str(sk)] = int(node.get("depth_level") or 0)
    return out


def _tag_kps_on_mapping(mapping, required_set: set[str]) -> set[str]:
    matched: set[str] = set()
    for t in getattr(mapping.ai_result, "proposed_tags", []) or []:
        if t.source_kp_id in required_set:
            matched.add(t.source_kp_id)
    for t in getattr(mapping, "human_tags", []) or []:
        if t.source_kp_id in required_set:
            matched.add(t.source_kp_id)
    return matched


def collect_approved_entries(
    mapping_store: MappingStore,
    kp_ids: Iterable[str],
    *,
    content_type: str,
    per_kp_limit: int = 50,
) -> dict[str, dict]:
    """content_id -> {mapping, matched_kps, first_kp}."""
    per_content: dict[str, dict] = {}
    kp_list = [k for k in kp_ids if k]
    kp_priority = {k: i for i, k in enumerate(kp_list)}

    for kp_id in kp_list:
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
    return per_content


def filter_entries_by_kg_tiers(
    entries: dict[str, dict],
    required_kp_ids: list[str],
    depth_by_kp: dict[str, int],
    *,
    required_set: set[str] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Intersection narrowing by depth tier (descending). Returns (entries_list, meta)."""
    required_set = required_set or set(required_kp_ids)
    tagged_depths = sorted(
        {depth_by_kp[k] for k in required_kp_ids if k in depth_by_kp},
        reverse=True,
    )
    meta: dict[str, Any] = {
        "retrieval_strategy": "kg_tiered_intersection",
        "tiers_processed": 0,
        "tier_depths": [],
        "stop_reason": "no_tagged_depths",
        "pool_size": 0,
    }
    if not tagged_depths:
        return [], meta

    tiers = tagged_depths[:MAX_TIER_PASSES]
    pool: list[dict] = []
    stop_reason = "max_tiers"

    for i, depth in enumerate(tiers):
        tier_kps = {k for k in required_kp_ids if depth_by_kp.get(k) == depth}
        if not tier_kps:
            continue

        if i == 0:
            pool = [
                e
                for e in entries.values()
                if _tag_kps_on_mapping(e["mapping"], tier_kps)
                or e["matched_kps"] & tier_kps
            ]
        else:
            narrowed = [
                e
                for e in pool
                if _tag_kps_on_mapping(e["mapping"], tier_kps)
                or e["matched_kps"] & tier_kps
            ]
            if not narrowed:
                stop_reason = "empty_tier_intersection"
                break
            pool = narrowed

        meta["tiers_processed"] = i + 1
        meta["tier_depths"].append(depth)
        meta["pool_size"] = len(pool)

        if len(pool) < MIN_POOL_BEFORE_STOP:
            stop_reason = "below_10"
            break

    meta["stop_reason"] = stop_reason
    meta["pool_size"] = len(pool)
    return pool, meta


def _make_body_loader() -> tuple[dict[str, str], Callable[[str], str]]:
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

    return body_cache, _body_for


def entries_to_citations(
    entries: list[dict],
    required_kp_ids: list[str],
    *,
    content_type: str,
    depth_by_kp: dict[str, int],
    total_cap: int | None = 8,
    byte_budget: int = TOTAL_BODY_BYTES_BUDGET,
    tier_pass: int = 0,
) -> list[dict]:
    if not entries:
        return []

    kp_priority = {k: i for i, k in enumerate(required_kp_ids)}
    required_set = set(required_kp_ids)

    for entry in entries:
        m = entry["mapping"]
        tag_kps: set[str] = set()
        for t in getattr(m.ai_result, "proposed_tags", []) or []:
            if t.source_kp_id in required_set:
                tag_kps.add(t.source_kp_id)
        for t in getattr(m, "human_tags", []) or []:
            if t.source_kp_id in required_set:
                tag_kps.add(t.source_kp_id)
        entry["matched_kps"] = entry.get("matched_kps", set()) | tag_kps
        entry["overlap"] = len(entry["matched_kps"])

    ranked = sorted(
        entries,
        key=lambda e: (-e["overlap"], kp_priority.get(e["first_kp"], 999)),
    )

    _, body_for = _make_body_loader()
    all_candidates: list[dict] = []
    for entry in ranked:
        if total_cap is not None and len(all_candidates) >= total_cap:
            break
        m = entry["mapping"]
        kp_id = entry["first_kp"]
        tag_role = "explain"
        for t in getattr(m.ai_result, "proposed_tags", []) or []:
            if t.source_kp_id == kp_id:
                tag_role = t.tag_role.value
                break
        else:
            for t in m.human_tags:
                if t.source_kp_id == kp_id:
                    tag_role = t.tag_role.value
                    break
        body = body_for(m.file_path)
        snippet = f"[{m.title}]\n{m.topic_name}\n\n{body}".strip()
        all_candidates.append(
            {
                "content_id": m.content_id,
                "title": m.title,
                "topic_name": m.topic_name,
                "kp_id": kp_id,
                "tag_role": tag_role,
                "snippet": snippet,
                "content_type": m.content_type or content_type,
                "kg_depth_level": depth_by_kp.get(kp_id, -1),
                "kg_tier_pass": tier_pass,
                "retrieval_strategy": "kg_tiered_intersection",
            }
        )

    out: list[dict] = []
    used_bytes = 0
    for c in all_candidates:
        cost = len(c["snippet"].encode("utf-8"))
        if used_bytes + cost > byte_budget and out:
            logger.warning(
                "KG citation body budget exceeded (used=%d, cap=%d); dropping trailing.",
                used_bytes,
                byte_budget,
            )
            break
        out.append(c)
        used_bytes += cost
    return out


def tiered_citations_for_content_type(
    mapping_store: MappingStore,
    required_kp_ids: list[str],
    *,
    course_id: str,
    content_type: str,
    per_kp_limit: int = 50,
) -> tuple[list[dict], dict[str, Any]]:
    required = [k for k in required_kp_ids if k]
    if not required:
        return [], {"retrieval_strategy": "kg_tiered_intersection", "pool_size": 0}

    depth_by_kp = depth_by_kp_from_graph(course_id)
    known = [k for k in required if k in depth_by_kp]
    if not known:
        logger.warning(
            "No KG depths for tagged KPs (course=%s); overlap fallback for %s",
            course_id,
            content_type,
        )
        fallback = build_citations_fn(
            mapping_store,
            per_kp_limit=per_kp_limit,
            total_cap=50,
            content_type=content_type,
        )
        return fallback(required), {
            "retrieval_strategy": "overlap_fallback",
            "pool_size": 0,
            "stop_reason": "no_kg_depths",
        }

    all_kp_entries = collect_approved_entries(
        mapping_store,
        required,
        content_type=content_type,
        per_kp_limit=per_kp_limit,
    )
    pool_entries, meta = filter_entries_by_kg_tiers(
        all_kp_entries,
        required,
        depth_by_kp,
    )
    tiers_done = int(meta.get("tiers_processed") or 0)
    citations = entries_to_citations(
        pool_entries,
        required,
        content_type=content_type,
        depth_by_kp=depth_by_kp,
        total_cap=None,
        tier_pass=tiers_done,
    )
    meta["content_type"] = content_type
    meta["candidates_before_cap"] = len(citations)
    return citations, meta


def merge_and_cap_citations(
    streams: list[tuple[list[dict], dict[str, Any]]],
    *,
    total_cap: int = 8,
    byte_budget: int = TOTAL_BODY_BYTES_BUDGET,
) -> tuple[list[dict], dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict] = []
    meta: dict[str, Any] = {"retrieval_strategy": "kg_tiered_intersection"}

    for citations, stream_meta in streams:
        for key, val in stream_meta.items():
            if key not in meta or key in ("content_type",):
                meta[key] = val
        for c in citations:
            cid = c["content_id"]
            if cid in seen:
                continue
            seen.add(cid)
            merged.append(c)

    meta["pool_size_before_cap"] = len(merged)
    out: list[dict] = []
    used_bytes = 0
    for c in merged:
        if len(out) >= total_cap:
            break
        cost = len(c["snippet"].encode("utf-8"))
        if used_bytes + cost > byte_budget and out:
            break
        out.append(c)
        used_bytes += cost

    meta["pool_size"] = len(out)
    meta["coding_count"] = sum(
        1 for c in out if (c.get("content_type") or "") == "coding_question"
    )
    meta["reading_count"] = sum(
        1 for c in out if (c.get("content_type") or "") == "reading_material"
    )
    return out, meta


def build_kg_tiered_citations_fn(
    mapping_store: MappingStore,
    *,
    course_id: str = DEFAULT_COURSE_ID,
    content_type: str = "coding_question",
    per_kp_limit: int = 50,
) -> Callable[[list[str]], list[dict]]:
    """Single content-type KG-tiered retriever."""

    def citations_for(required_kp_ids: list[str]) -> list[dict]:
        result, meta = tiered_citations_for_content_type(
            mapping_store,
            required_kp_ids,
            course_id=course_id,
            content_type=content_type,
            per_kp_limit=per_kp_limit,
        )
        citations_for.last_meta = meta  # type: ignore[attr-defined]
        return result

    citations_for.last_meta = {}  # type: ignore[attr-defined]
    return citations_for


def build_coding_interview_citations_fn(
    mapping_store: MappingStore,
    *,
    course_id: str = DEFAULT_COURSE_ID,
    per_kp_limit: int = 50,
    total_cap: int = 8,
) -> Callable[[list[str]], list[dict]]:
    """CODING interview: tiered coding_question + reading_material, merged."""

    def citations_for(required_kp_ids: list[str]) -> list[dict]:
        coding, meta_c = tiered_citations_for_content_type(
            mapping_store,
            required_kp_ids,
            course_id=course_id,
            content_type="coding_question",
            per_kp_limit=per_kp_limit,
        )
        reading, meta_r = tiered_citations_for_content_type(
            mapping_store,
            required_kp_ids,
            course_id=course_id,
            content_type="reading_material",
            per_kp_limit=per_kp_limit,
        )
        out, meta = merge_and_cap_citations(
            [(coding, meta_c), (reading, meta_r)],
            total_cap=total_cap,
        )
        meta["coding_stream"] = meta_c
        meta["reading_stream"] = meta_r
        citations_for.last_meta = meta  # type: ignore[attr-defined]
        return out

    citations_for.last_meta = {}  # type: ignore[attr-defined]
    return citations_for
