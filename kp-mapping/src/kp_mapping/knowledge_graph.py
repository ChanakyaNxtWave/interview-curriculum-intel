from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .kp_catalog import load_catalog

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
CURRICULUM_DIR = REPO_ROOT / "curriculum"

COURSE_DIRS: dict[str, str] = {
    "Programming Foundations": "ProgrammingFoundations",
}

DEFAULT_KP_JSON = REPO_ROOT / "curriculum" / "KPs-ProgrammingFoundations.json"


def _source_kp_id_by_node_id() -> dict[str, str]:
    if not DEFAULT_KP_JSON.is_file():
        return {}
    catalog = load_catalog(DEFAULT_KP_JSON)
    return {
        kp.knowledge_node_id: kp.source_kp_id
        for kp in catalog.knowledge_points
        if kp.knowledge_node_id
    }


class KnowledgeGraphError(ValueError):
    """Invalid knowledge graph data."""


def _slugify_course(title: str) -> str:
    return (
        title.strip()
        .lower()
        .replace("&", "and")
        .replace("/", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _course_title_for_slug(course_slug: str) -> str | None:
    for title in COURSE_DIRS:
        if _slugify_course(title) == course_slug:
            return title
    return None


def knowledge_graph_path(course_slug: str) -> Path | None:
    title = _course_title_for_slug(course_slug)
    if not title:
        return None
    dir_name = COURSE_DIRS.get(title)
    if not dir_name:
        return None
    path = CURRICULUM_DIR / dir_name / f"{course_slug}_knowledge_nodes.json"
    return path if path.is_file() else None


def load_knowledge_graph_raw(course_slug: str) -> dict[str, Any] | None:
    path = knowledge_graph_path(course_slug)
    if not path:
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_knowledge_graph(nodes: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    for node in nodes:
        nid = node.get("knowledge_node_id")
        if not nid:
            raise KnowledgeGraphError("Node missing knowledge_node_id")
        if nid in ids:
            raise KnowledgeGraphError(f"Duplicate knowledge_node_id: {nid}")
        ids.add(nid)

    for node in nodes:
        nid = node["knowledge_node_id"]
        for prereq in node.get("prerequisites") or []:
            if prereq not in ids:
                raise KnowledgeGraphError(
                    f"Node {nid} references unknown prerequisite {prereq}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {n["knowledge_node_id"]: n for n in nodes}

    def dfs(nid: str) -> None:
        if nid in visited:
            return
        if nid in visiting:
            raise KnowledgeGraphError(f"Cycle detected involving node {nid}")
        visiting.add(nid)
        for prereq in by_id[nid].get("prerequisites") or []:
            dfs(prereq)
        visiting.remove(nid)
        visited.add(nid)

    for nid in ids:
        dfs(nid)


def compute_depth_levels(nodes: list[dict[str, Any]]) -> dict[str, int]:
    by_id = {n["knowledge_node_id"]: n for n in nodes}
    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        prereqs = by_id[nid].get("prerequisites") or []
        if not prereqs:
            memo[nid] = 0
            return 0
        memo[nid] = 1 + max(depth(p) for p in prereqs)
        return memo[nid]

    return {nid: depth(nid) for nid in by_id}


def enrich_graph_payload(raw: dict[str, Any], course_id: str) -> dict[str, Any]:
    nodes_raw = raw.get("knowledge_nodes") or []
    if not nodes_raw:
        raise KnowledgeGraphError("knowledge_nodes array is empty or missing")

    validate_knowledge_graph(nodes_raw)
    depths = compute_depth_levels(nodes_raw)
    kp_by_node = _source_kp_id_by_node_id()

    enriched_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    for node in nodes_raw:
        nid = node["knowledge_node_id"]
        prereqs = node.get("prerequisites") or []
        entry: dict[str, Any] = {
            "knowledge_node_id": nid,
            "label": node.get("label", ""),
            "description": node.get("description", ""),
            "prerequisites": prereqs,
            "depth_level": depths[nid],
        }
        source_kp_id = kp_by_node.get(nid)
        if source_kp_id:
            entry["source_kp_id"] = source_kp_id
        enriched_nodes.append(entry)
        for prereq in prereqs:
            edges.append({"source": prereq, "target": nid})

    depth_counts: dict[str, int] = {}
    for lv in depths.values():
        key = str(lv)
        depth_counts[key] = depth_counts.get(key, 0) + 1

    max_depth = max(depths.values()) if depths else 0

    depth_level_definitions = raw.get("depth_level_definitions")
    if not depth_level_definitions:
        depth_level_definitions = [
            {
                "level": lv,
                "label": f"Level {lv}",
                "node_count": depth_counts.get(str(lv), 0),
            }
            for lv in range(max_depth + 1)
        ]

    return {
        "course_id": course_id,
        "nodes": enriched_nodes,
        "edges": edges,
        "stats": {
            "node_count": len(enriched_nodes),
            "edge_count": len(edges),
            "max_depth": max_depth,
            "depth_counts": depth_counts,
        },
        "depth_level_definitions": depth_level_definitions,
    }


def load_knowledge_graph(course_slug: str) -> dict[str, Any] | None:
    raw = load_knowledge_graph_raw(course_slug)
    if raw is None:
        return None
    return enrich_graph_payload(raw, course_slug)


def knowledge_graph_node_count(course_slug: str) -> int | None:
    raw = load_knowledge_graph_raw(course_slug)
    if raw is None:
        return None
    nodes = raw.get("knowledge_nodes") or []
    return len(nodes) if nodes else None
