"""
Node tagger agent — 2-phase LLM pipeline for uncovered interview questions.

Phase 1: Coverage Analysis
  LLM receives question + compact catalog.
  Returns: existing node IDs that cover the question, gap skills, coverage_status.

Phase 2: New KP Generation  (skipped when coverage_status == "full")
  LLM receives gap descriptions + full catalog.
  Returns: new KnowledgeNode definitions with temp_ids → resolved to real UUIDs.

Phase 3: Prerequisite Closure (no LLM, pure graph walk)
  Collect all prerequisite existing nodes for the terminal IDs identified.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from ..llm_client import LLMError, chat_completion, parse_json_response
from .graph import KnowledgeGraph, compute_depth_level
from .prompts import (
    COVERAGE_ANALYZER_SYSTEM,
    COVERAGE_ANALYZER_USER_TEMPLATE,
    NEW_KP_GENERATOR_SYSTEM,
    NEW_KP_GENERATOR_USER_TEMPLATE,
)
from .schemas import AgentResult, KnowledgeNode, QuestionInput


def run_agent(
    inp: QuestionInput,
    kg: KnowledgeGraph,
    *,
    model: str | None = None,
) -> AgentResult:
    """Run full 3-phase pipeline and return AgentResult."""
    # Phase 1: coverage analysis
    terminal_ids, gap_skills, coverage_status = _analyze_coverage(inp, kg, model=model)

    # Phase 2: generate new KPs for gaps
    new_nodes: list[KnowledgeNode] = []
    if gap_skills and coverage_status != "full":
        new_nodes = _generate_new_kps(inp, kg, gap_skills, terminal_ids, model=model)

    # Phase 3: prerequisite closure over existing graph
    all_terminal_existing = list(terminal_ids)
    for node in new_nodes:
        for prereq_id in node.prerequisites:
            if kg.has_node(prereq_id) and prereq_id not in all_terminal_existing:
                all_terminal_existing.append(prereq_id)

    existing_closure = kg.prerequisite_closure(all_terminal_existing)

    reasoning = (
        f"Coverage: {coverage_status}. "
        f"Terminal existing KPs: {terminal_ids}. "
        f"Gaps: {[g.get('label', '') for g in gap_skills] if gap_skills else 'none'}. "
        f"New KPs created: {len(new_nodes)}. "
        f"Existing closure size: {len(existing_closure)}."
    )

    return AgentResult(
        question=inp.question,
        coverage_status=coverage_status,
        existing_node_ids=existing_closure,
        new_nodes=new_nodes,
        reasoning=reasoning,
    )


def _analyze_coverage(
    inp: QuestionInput,
    kg: KnowledgeGraph,
    *,
    model: str | None = None,
) -> tuple[list[str], list[dict], str]:
    """Phase 1. Returns (terminal_existing_ids, gap_skills, coverage_status)."""
    solution_block = (
        f"\nReference solution (Python):\n```python\n{inp.solution}\n```\n"
        if inp.solution
        else ""
    )
    user = COVERAGE_ANALYZER_USER_TEMPLATE.format(
        question=inp.question,
        solution_block=solution_block,
        catalog=kg.catalog_compact(),
    )
    result = chat_completion(
        [
            {"role": "system", "content": COVERAGE_ANALYZER_SYSTEM},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0,
        max_tokens=2048,
    )
    payload = parse_json_response(result.content)

    existing_ids_set = {n.knowledge_node_id for n in kg.nodes}
    covered_ids = [
        str(nid).strip()
        for nid in (payload.get("covered_node_ids") or [])
        if str(nid).strip() in existing_ids_set
    ]
    gap_skills: list[dict] = payload.get("gap_skills") or []
    coverage_status: str = payload.get("coverage_status", "partial")

    if not gap_skills and covered_ids:
        coverage_status = "full"
    elif not covered_ids and gap_skills:
        coverage_status = "none"
    elif covered_ids and gap_skills:
        coverage_status = "partial"

    return covered_ids, gap_skills, coverage_status


def _generate_new_kps(
    inp: QuestionInput,
    kg: KnowledgeGraph,
    gap_skills: list[dict],
    covered_existing_ids: list[str],
    *,
    model: str | None = None,
) -> list[KnowledgeNode]:
    """Phase 2. Ask LLM to define new KnowledgeNode objects for each gap."""
    gaps_block = "\n".join(
        f"- label: {g.get('label', '')}\n"
        f"  description: {g.get('description', '')}\n"
        f"  suggested_prerequisites: {g.get('suggested_prerequisite_labels', [])}"
        for g in gap_skills
    )
    covered_nodes = kg.nodes_by_ids(covered_existing_ids)
    covered_block = (
        "\n".join(f"- {n.knowledge_node_id}: {n.label}" for n in covered_nodes)
        or "none"
    )
    user = NEW_KP_GENERATOR_USER_TEMPLATE.format(
        question=inp.question,
        gaps_block=gaps_block,
        covered_block=covered_block,
        catalog=kg.catalog_full(),
    )
    result = chat_completion(
        [
            {"role": "system", "content": NEW_KP_GENERATOR_SYSTEM},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0,
        max_tokens=4096,
    )
    payload = parse_json_response(result.content)
    raw_nodes: list[dict] = payload.get("new_nodes") or []
    if not raw_nodes:
        return []
    return _materialise_new_nodes(raw_nodes, kg)


def _materialise_new_nodes(raw_nodes: list[dict], kg: KnowledgeGraph) -> list[KnowledgeNode]:
    """Assign real UUIDs, resolve temp_id references, compute depth_levels."""
    existing_ids = {n.knowledge_node_id for n in kg.nodes}

    temp_to_uuid: dict[str, str] = {}
    for raw in raw_nodes:
        temp_id = str(raw.get("temp_id", "")).strip()
        if temp_id and temp_id not in temp_to_uuid:
            temp_to_uuid[temp_id] = str(uuid.uuid4())

    new_nodes: list[KnowledgeNode] = []
    for raw in raw_nodes:
        temp_id = str(raw.get("temp_id", "")).strip()
        real_id = temp_to_uuid.get(temp_id, str(uuid.uuid4()))
        label = str(raw.get("label", "")).strip()
        description = str(raw.get("description", "")).strip()
        if not label or not description:
            continue

        prereqs: list[str] = []
        for pid in (raw.get("prerequisite_ids") or []):
            pid = str(pid).strip()
            if pid in existing_ids:
                prereqs.append(pid)
            elif pid in temp_to_uuid:
                prereqs.append(temp_to_uuid[pid])

        new_nodes.append(
            KnowledgeNode(
                knowledge_node_id=real_id,
                label=label,
                description=description,
                prerequisites=prereqs,
                depth_level=0,
            )
        )

    primary_by_id = {n.knowledge_node_id: n for n in kg.nodes}
    new_by_id = {n.knowledge_node_id: n for n in new_nodes}
    for node in new_nodes:
        node.depth_level = compute_depth_level(
            node.knowledge_node_id,
            primary_by_id=primary_by_id,
            extra_by_id=new_by_id,
        )

    return new_nodes
