#!/usr/bin/env python3
"""Write computed depth_level and depth_level_definitions into knowledge_nodes JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kp_mapping.knowledge_graph import (  # noqa: E402
    KnowledgeGraphError,
    compute_depth_levels,
    enrich_graph_payload,
    knowledge_graph_path,
    load_knowledge_graph_raw,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--course-id",
        default="programming_foundations",
        help="Course slug (default: programming_foundations)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing file",
    )
    args = parser.parse_args()

    path = knowledge_graph_path(args.course_id)
    if not path:
        print(f"No knowledge graph file for course {args.course_id!r}", file=sys.stderr)
        return 1

    raw = load_knowledge_graph_raw(args.course_id)
    if not raw:
        print("Failed to load graph", file=sys.stderr)
        return 1

    try:
        payload = enrich_graph_payload(raw, args.course_id)
    except KnowledgeGraphError as exc:
        print(f"Invalid graph: {exc}", file=sys.stderr)
        return 1

    depths = compute_depth_levels(raw.get("knowledge_nodes") or [])
    by_id = {n["knowledge_node_id"]: n for n in raw["knowledge_nodes"]}
    for node in raw["knowledge_nodes"]:
        nid = node["knowledge_node_id"]
        node["depth_level"] = depths[nid]

    raw["depth_level_definitions"] = payload["depth_level_definitions"]

    stats = payload["stats"]
    print(
        f"Nodes: {stats['node_count']}, edges: {stats['edge_count']}, "
        f"max_depth: {stats['max_depth']}"
    )
    for defn in payload["depth_level_definitions"]:
        print(f"  L{defn['level']}: {defn['node_count']} nodes — {defn['label']}")

    if args.dry_run:
        return 0

    with path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
