from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kp_mapping.theory.kg_citation_retrieval import (
    MIN_POOL_BEFORE_STOP,
    filter_entries_by_kg_tiers,
    merge_and_cap_citations,
)


def _entry(content_id: str, matched_kps: set[str]) -> dict:
    mapping = SimpleNamespace(
        ai_result=SimpleNamespace(proposed_tags=[]),
        human_tags=[],
    )
    return {
        "mapping": mapping,
        "matched_kps": matched_kps,
        "first_kp": next(iter(matched_kps)),
    }


def test_filter_highest_depth_first_then_intersect():
    depth_by_kp = {"KP_A": 5, "KP_B": 3, "KP_C": 1}
    entries = {
        "c1": _entry("c1", {"KP_A"}),
        "c2": _entry("c2", {"KP_A", "KP_B"}),
        "c3": _entry("c3", {"KP_B"}),
        "c4": _entry("c4", {"KP_C"}),
    }
    pool, meta = filter_entries_by_kg_tiers(
        entries,
        ["KP_A", "KP_B", "KP_C"],
        depth_by_kp,
    )
    pool_ids = {
        cid
        for cid, ent in entries.items()
        if ent in pool
    }
    assert pool_ids == {"c1", "c2"}  # highest tier (KP_A); pool < 10 → stop early
    assert meta["tier_depths"][0] == 5
    assert meta["stop_reason"] == "below_10"


def test_filter_stops_below_10_candidates():
    depth_by_kp = {f"KP_{i}": i for i in range(4)}
    entries = {f"c{i}": _entry(f"c{i}", {f"KP_{i}"}) for i in range(4)}
    # All four share depth tiers; after intersecting we shrink quickly
    pool, meta = filter_entries_by_kg_tiers(
        entries,
        list(depth_by_kp.keys()),
        depth_by_kp,
    )
    assert len(pool) < MIN_POOL_BEFORE_STOP or meta["stop_reason"] in {
        "below_10",
        "max_tiers",
        "empty_tier_intersection",
    }


def test_filter_empty_intersection_keeps_previous_pool():
    depth_by_kp = {"KP_HIGH": 10, "KP_LOW": 1}
    # ≥10 entries at highest tier so we reach the lower tier pass
    entries = {f"c{i}": _entry(f"c{i}", {"KP_HIGH"}) for i in range(10)}
    entries["also_high"] = _entry("also_high", {"KP_HIGH"})
    pool, meta = filter_entries_by_kg_tiers(
        entries,
        ["KP_HIGH", "KP_LOW"],
        depth_by_kp,
    )
    assert len(pool) == 11
    assert meta["stop_reason"] == "empty_tier_intersection"


def test_filter_max_four_tiers():
    depth_by_kp = {f"KP_{i}": i for i in range(8)}
    entries = {
        f"c{i}": _entry(f"c{i}", {f"KP_{i}"})
        for i in range(8)
    }
    _, meta = filter_entries_by_kg_tiers(
        entries,
        list(depth_by_kp.keys()),
        depth_by_kp,
    )
    assert meta["tiers_processed"] <= 4
    assert len(meta["tier_depths"]) <= 4


def test_merge_dedupes_and_caps():
    coding = [
        {"content_id": "a", "snippet": "x" * 100, "content_type": "coding_question"},
        {"content_id": "b", "snippet": "y" * 100, "content_type": "coding_question"},
    ]
    reading = [
        {"content_id": "b", "snippet": "z" * 100, "content_type": "reading_material"},
        {"content_id": "c", "snippet": "w" * 100, "content_type": "reading_material"},
    ]
    merged, meta = merge_and_cap_citations(
        [(coding, {"pool_size": 2}), (reading, {"pool_size": 2})],
        total_cap=2,
        byte_budget=10_000,
    )
    assert len(merged) == 2
    assert {c["content_id"] for c in merged} == {"a", "b"}
    assert meta["coding_count"] == 2
    assert meta["reading_count"] == 0


@patch("kp_mapping.theory.kg_citation_retrieval.build_citations_fn")
@patch("kp_mapping.theory.kg_citation_retrieval.depth_by_kp_from_graph")
def test_tiered_fallback_when_no_kg_depths(mock_depth, mock_build_fn):
    from kp_mapping.theory.kg_citation_retrieval import tiered_citations_for_content_type

    mock_depth.return_value = {}
    fallback_fn = MagicMock(return_value=[{"content_id": "fb"}])
    mock_build_fn.return_value = fallback_fn
    store = MagicMock()

    result, meta = tiered_citations_for_content_type(
        store,
        ["KP_UNKNOWN"],
        course_id="programming_foundations",
        content_type="coding_question",
    )

    assert result == [{"content_id": "fb"}]
    assert meta["retrieval_strategy"] == "overlap_fallback"
    mock_build_fn.assert_called_once()
