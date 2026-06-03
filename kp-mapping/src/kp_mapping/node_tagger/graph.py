"""
In-memory knowledge graph for node_tagger pipeline.

Loads from programming_foundations_knowledge_nodes.json and provides:
  - prerequisite_closure()   — BFS backward, topological order
  - catalog_compact()        — "id | depth | label" format for LLM phase 1
  - catalog_full()           — full details for LLM phase 2
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from ..knowledge_graph import load_knowledge_graph_raw
from .schemas import KnowledgeNode


class KnowledgeGraph:
    def __init__(self, nodes: list[KnowledgeNode]) -> None:
        self.nodes = nodes
        self._by_id: dict[str, KnowledgeNode] = {n.knowledge_node_id: n for n in nodes}

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        return self._by_id.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._by_id

    def nodes_by_ids(self, ids: list[str]) -> list[KnowledgeNode]:
        return [self._by_id[nid] for nid in ids if nid in self._by_id]

    def prerequisite_closure(self, terminal_ids: list[str]) -> list[str]:
        """Return all nodes reachable by walking prerequisites from terminal_ids.
        Topologically ordered (roots first, terminals last)."""
        valid = [nid for nid in terminal_ids if nid in self._by_id]
        if not valid:
            return []
        visited: set[str] = set(valid)
        queue: deque[str] = deque(valid)
        while queue:
            nid = queue.popleft()
            node = self._by_id.get(nid)
            if not node:
                continue
            for prereq_id in node.prerequisites:
                if prereq_id not in visited and prereq_id in self._by_id:
                    visited.add(prereq_id)
                    queue.append(prereq_id)
        return _topological_order(visited, self._by_id)

    def catalog_compact(self) -> str:
        """One line per node: id | depth | label. Low token cost for phase 1."""
        lines = [
            f"{n.knowledge_node_id} | depth={n.depth_level} | {n.label}"
            for n in sorted(self.nodes, key=lambda n: (n.depth_level, n.label))
        ]
        return "\n".join(lines)

    def catalog_full(self) -> str:
        """Full details for prerequisite-picking in phase 2."""
        lines = [
            f"- id: {n.knowledge_node_id}\n"
            f"  label: {n.label}\n"
            f"  description: {n.description}\n"
            f"  depth_level: {n.depth_level}"
            for n in sorted(self.nodes, key=lambda n: (n.depth_level, n.label))
        ]
        return "\n".join(lines)


def load_node_tagger_graph(kg_json_path: str | Path) -> KnowledgeGraph:
    """Load KnowledgeGraph from the knowledge_nodes.json file."""
    raw = load_knowledge_graph_raw_from_path(kg_json_path)
    nodes = [
        KnowledgeNode(
            knowledge_node_id=n["knowledge_node_id"],
            label=n.get("label", ""),
            description=n.get("description", ""),
            prerequisites=list(n.get("prerequisites") or []),
            depth_level=int(n.get("depth_level") or 0),
        )
        for n in raw
    ]
    return KnowledgeGraph(nodes)


def load_knowledge_graph_raw_from_path(path: str | Path) -> list[dict[str, Any]]:
    """Read and parse the knowledge_nodes JSON, returning the raw node list."""
    import json

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Knowledge graph JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("knowledge_nodes") or []


def compute_depth_level(
    node_id: str,
    primary_by_id: dict[str, KnowledgeNode],
    extra_by_id: dict[str, KnowledgeNode] | None = None,
    _visited: frozenset[str] | None = None,
) -> int:
    """Recursive depth_level = max(prereq_depths) + 1. Cycle-safe."""
    all_by_id = {**primary_by_id, **(extra_by_id or {})}
    _visited = _visited or frozenset()
    if node_id in _visited:
        return 0
    node = all_by_id.get(node_id)
    if not node or not node.prerequisites:
        return 1
    nv = _visited | {node_id}
    max_prereq = max(
        compute_depth_level(p, primary_by_id, extra_by_id, nv)
        for p in node.prerequisites
    )
    return max_prereq + 1


def _topological_order(node_ids: set[str], by_id: dict[str, KnowledgeNode]) -> list[str]:
    """Kahn's algorithm — roots (no prerequisites) first."""
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = defaultdict(list)
    for nid in node_ids:
        node = by_id.get(nid)
        if not node:
            continue
        for prereq_id in node.prerequisites:
            if prereq_id in node_ids:
                adj[prereq_id].append(nid)
                in_degree[nid] += 1

    queue: deque[str] = deque(sorted(nid for nid, deg in in_degree.items() if deg == 0))
    ordered: list[str] = []
    while queue:
        nid = queue.popleft()
        ordered.append(nid)
        for neighbor in sorted(adj[nid]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(node_ids):
        ordered += sorted(node_ids - set(ordered))
    return ordered
