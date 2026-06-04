from __future__ import annotations

import json
import logging
from typing import Any, Callable

from ..llm_client import LLMError, chat_completion, parse_json_response
from ..models import KPCatalog
from ..theory.store import TheoryStore
from .matcher import KpMatcher
from .prompts import (
    IPA_SYSTEM_PROMPT,
    LTA_SYSTEM_PROMPT,
    NORMALIZATION_SYSTEM_PROMPT,
    get_kp_proposal_system_prompt,
)
from .store import KgExpansionStore

logger = logging.getLogger("kp_mapping.kg_expansion")

PROMPT_VERSION = "kg-expansion-ipa-lta-v4"


def _llm_json(system: str, user: str, *, model: str | None = None) -> tuple[dict, str]:
    completion = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0.2,
        max_tokens=4096,
    )
    return parse_json_response(completion.content), completion.model_label


def run_ipa(question_text: str, *, model: str | None = None) -> tuple[dict, str]:
    user = f"Question:\n{question_text.strip()}\n\nReturn JSON with reasoning_steps."
    return _llm_json(IPA_SYSTEM_PROMPT, user, model=model)


def run_lta(reasoning_steps: list[dict], *, model: str | None = None) -> tuple[dict, str]:
    user = (
        "Reasoning steps from IPA:\n"
        f"{json.dumps(reasoning_steps, indent=2)}\n\n"
        "Return JSON with skills and prerequisites."
    )
    return _llm_json(LTA_SYSTEM_PROMPT, user, model=model)


def run_normalization(skills: list[dict], *, model: str | None = None) -> tuple[dict, str]:
    user = (
        "Skills from LTA:\n"
        f"{json.dumps(skills, indent=2)}\n\n"
        "Return JSON with normalized_skills."
    )
    return _llm_json(NORMALIZATION_SYSTEM_PROMPT, user, model=model)


def run_kp_proposal(
    *,
    question_text: str,
    normalized_skills: list[dict],
    matcher: KpMatcher,
    model: str | None = None,
    feedback_context: str = "",
) -> tuple[dict, str]:
    user = (
        f"Question:\n{question_text.strip()}\n\n"
        f"Normalized skills:\n{json.dumps(normalized_skills, indent=2)}\n\n"
        f"Catalog excerpt:\n{matcher.catalog_prompt_excerpt()}\n\n"
        "Return JSON with catalog_matches and new_kps."
    )
    return _llm_json(
        get_kp_proposal_system_prompt(feedback_context), user, model=model
    )


def _skill_id_to_proposed_node(
    skill_ids: list[str],
    skill_nodes: dict[str, str],
) -> list[str]:
    prereqs: list[str] = []
    for sid in skill_ids:
        nid = skill_nodes.get(sid)
        if nid and nid not in prereqs:
            prereqs.append(nid)
    return prereqs


def _resolve_prerequisite_nodes(
    prereq_skill_ids: list[str],
    *,
    matcher: KpMatcher,
    skill_nodes: dict[str, str],
) -> list[str]:
    """Map prerequisite_skill_ids to knowledge_node_ids (catalog + proposed LTA skills)."""
    lta_ids, catalog_ids = matcher.split_prerequisite_skill_ids(
        prereq_skill_ids, skill_nodes=skill_nodes
    )
    nodes = _skill_id_to_proposed_node(lta_ids, skill_nodes)
    nodes.extend(matcher.resolve_catalog_ids(catalog_ids))
    return nodes


def _merge_prerequisite_skill_ids(item: dict) -> list[str]:
    """Collect prerequisite_skill_ids; merge legacy prerequisite_catalog_kp_ids."""
    out: list[str] = []
    for raw in item.get("prerequisite_skill_ids") or []:
        sid = str(raw).strip()
        if sid and sid not in out:
            out.append(sid)
    for raw in item.get("prerequisite_catalog_kp_ids") or []:
        sid = str(raw).strip()
        if sid and sid not in out:
            out.append(sid)
    return out


def apply_kp_proposal(
    proposal: dict,
    *,
    matcher: KpMatcher,
    normalized_skills: list[dict],
) -> tuple[list[dict], dict]:
    """Turn LLM proposal into mapping rows; register new KPs in matcher."""
    mappings: list[dict] = []
    skill_nodes: dict[str, str] = {}

    new_kps = proposal.get("new_kps") or []
    staged: list[dict] = []

    for nk in new_kps:
        if not isinstance(nk, dict):
            continue
        label = str(nk.get("label") or "").strip()
        if not label:
            continue
        description = str(nk.get("description") or "").strip()
        skill_ids = [str(s) for s in (nk.get("skill_ids") or [])]
        staged.append(
            {
                "label": label,
                "description": description,
                "skill_ids": skill_ids,
                "prereq_skill_ids": _merge_prerequisite_skill_ids(nk),
            }
        )

    registrations: list[dict] = []
    for item in staged:
        label = item["label"]
        existing = matcher.match_proposed(label)
        if existing:
            reg = existing
        else:
            reg = matcher.register_proposed(
                label=label,
                description=item["description"],
                prerequisites=[],
            )
        for sid in item["skill_ids"]:
            skill_nodes[sid] = reg["knowledge_node_id"]
        registrations.append({"item": item, "reg": reg})

    for row in registrations:
        item = row["item"]
        reg = row["reg"]
        prereq_nodes = _resolve_prerequisite_nodes(
            item["prereq_skill_ids"],
            matcher=matcher,
            skill_nodes=skill_nodes,
        )
        for entry in matcher._proposed_by_label.values():
            if entry["proposed_kp_id"] == reg["proposed_kp_id"]:
                entry["prerequisites"] = prereq_nodes
                break
        reg["prerequisites"] = prereq_nodes
        mappings.append(
            {
                "skill_id": ",".join(item["skill_ids"]) or "proposed",
                "normalized_statement": reg["label"],
                "prerequisite_skill_ids": item["prereq_skill_ids"],
                **reg,
            }
        )

    seen_required: set[str] = set()
    for kp_id in proposal.get("required_catalog_kp_ids") or []:
        kid = str(kp_id).strip()
        if not kid or kid in seen_required:
            continue
        seen_required.add(kid)
        kp = matcher._catalog_by_id.get(kid)
        if not kp:
            continue
        mappings.append(
            {
                "skill_id": "required",
                "normalized_statement": kp.label,
                "match_type": "required_catalog",
                "similarity": 1.0,
                "source_kp_id": kp.source_kp_id,
                "knowledge_node_id": kp.knowledge_node_id,
                "label": kp.label,
            }
        )

    for cm in proposal.get("catalog_matches") or []:
        if not isinstance(cm, dict):
            continue
        kp_id = str(cm.get("source_kp_id") or "").strip()
        if not kp_id:
            continue
        kp = matcher._catalog_by_id.get(kp_id)
        if not kp:
            continue
        cm_prereqs = _merge_prerequisite_skill_ids(cm)
        mappings.append(
            {
                "skill_id": "catalog",
                "normalized_statement": kp.label,
                "match_type": "existing_catalog",
                "similarity": 1.0,
                "source_kp_id": kp.source_kp_id,
                "knowledge_node_id": kp.knowledge_node_id,
                "label": kp.label,
                "prerequisite_skill_ids": cm_prereqs,
                "rationale": str(cm.get("rationale") or ""),
            }
        )
        for prereq_id in cm_prereqs:
            if not str(prereq_id).strip().startswith("KP_GLOBAL_"):
                continue
            pk = matcher._catalog_by_id.get(str(prereq_id).strip())
            if not pk or pk.source_kp_id in seen_required:
                continue
            seen_required.add(pk.source_kp_id)
            mappings.append(
                {
                    "skill_id": "required",
                    "normalized_statement": pk.label,
                    "match_type": "required_catalog",
                    "similarity": 1.0,
                    "source_kp_id": pk.source_kp_id,
                    "knowledge_node_id": pk.knowledge_node_id,
                    "label": pk.label,
                }
            )

    for ns in normalized_skills:
        statement = str(ns.get("normalized_statement") or "").strip()
        skill_id = str(ns.get("skill_id") or "")
        if not statement:
            continue
        already = any(
            m.get("normalized_statement", "").lower() == statement.lower()
            or skill_id in (m.get("skill_id") or "")
            for m in mappings
        )
        if already:
            continue
        match = matcher.match_catalog(statement)
        mappings.append(
            {
                "skill_id": skill_id,
                "normalized_statement": statement,
                **match,
            }
        )

    return mappings, proposal


def collect_uncovered_questions(
    theory_store: TheoryStore,
    coding_store: TheoryStore,
    *,
    limit: int | None = None,
) -> list[dict]:
    items: list[dict] = []
    for store, qt in ((theory_store, "THEORY"), (coding_store, "CODING")):
        rows = store.list_tags(verdict="not_covered", limit=limit or 500, offset=0)
        for r in rows:
            items.append(
                {
                    "row_key": r["row_key"],
                    "question_type": qt,
                    "question_text": r.get("question_text") or "",
                    "verdict": r.get("verdict"),
                    "review_status": r.get("review_status"),
                }
            )
    if limit is not None:
        return items[:limit]
    return items


def process_question(
    *,
    question_text: str,
    matcher: KpMatcher,
    model: str | None = None,
    feedback_context: str = "",
) -> tuple[dict, dict, dict, dict, list[dict], str]:
    ipa, model_label = run_ipa(question_text, model=model)
    reasoning_steps = ipa.get("reasoning_steps") or []

    lta, _ = run_lta(reasoning_steps, model=model)
    skills = lta.get("skills") or []

    normalized, _ = run_normalization(skills, model=model)
    normalized_skills = normalized.get("normalized_skills") or []

    proposal, _ = run_kp_proposal(
        question_text=question_text,
        normalized_skills=normalized_skills,
        matcher=matcher,
        model=model,
        feedback_context=feedback_context,
    )
    mappings, proposal = apply_kp_proposal(
        proposal,
        matcher=matcher,
        normalized_skills=normalized_skills,
    )

    return ipa, lta, normalized, proposal, mappings, model_label


def _persist_proposed_from_matcher(
    run_id: int,
    matcher: KpMatcher,
    expansion_store: KgExpansionStore,
) -> None:
    for entry in matcher._proposed_by_label.values():
        expansion_store.upsert_proposed_kp(
            run_id=run_id,
            proposed_kp_id=entry["proposed_kp_id"],
            label=entry["label"],
            description=entry["description"],
            knowledge_node_id=entry["knowledge_node_id"],
        )
        expansion_store.upsert_proposed_node(
            run_id=run_id,
            knowledge_node_id=entry["knowledge_node_id"],
            label=entry["label"],
            description=entry["description"],
            prerequisites=list(entry.get("prerequisites") or []),
            proposed_kp_id=entry["proposed_kp_id"],
        )


def run_expansion(
    *,
    run_id: int,
    course_id: str,
    questions: list[dict],
    catalog: KPCatalog,
    expansion_store: KgExpansionStore,
    model: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    from .fewshot import maybe_update_fewshot
    # Apply any pending fewshot updates before the run so current prompts benefit.
    maybe_update_fewshot(expansion_store)
    # Load rejection context once per run; injected into every KP proposal call.
    feedback_context = expansion_store.get_rejection_patterns(limit=20)

    matcher = KpMatcher(catalog)
    expansion_store.update_run(run_id, status="running")
    processed = 0
    errors = 0
    new_kp_count = 0
    matched_catalog = 0
    unmatched_count = 0
    model_label = ""

    try:
        for q in questions:
            row_key = q["row_key"]
            question_text = q.get("question_text") or ""
            question_type = q.get("question_type") or "THEORY"
            try:
                ipa, lta, normalized, proposal, mappings, model_label = process_question(
                    question_text=question_text,
                    matcher=matcher,
                    model=model,
                    feedback_context=feedback_context,
                )
                for m in mappings:
                    mt = m.get("match_type")
                    if mt in ("new", "existing_proposed"):
                        new_kp_count += 1
                    elif mt == "existing_catalog":
                        matched_catalog += 1
                    elif mt == "unmatched":
                        unmatched_count += 1

                normalized_saved = {
                    **normalized,
                    "proposal": proposal,
                }
                expansion_store.save_question_result(
                    run_id=run_id,
                    row_key=row_key,
                    question_type=question_type,
                    question_text=question_text,
                    ipa=ipa,
                    lta=lta,
                    normalized=normalized_saved,
                    mappings=mappings,
                    error_message=None,
                )
            except (LLMError, json.JSONDecodeError, ValueError) as exc:
                errors += 1
                logger.exception("Gap expansion failed for %s: %s", row_key, exc)
                expansion_store.save_question_result(
                    run_id=run_id,
                    row_key=row_key,
                    question_type=question_type,
                    question_text=question_text,
                    ipa={},
                    lta={},
                    normalized={},
                    mappings=[],
                    error_message=str(exc),
                )
            processed += 1
            expansion_store.update_run(run_id, processed_count=processed)
            if on_progress:
                on_progress(processed, len(questions))

        _persist_proposed_from_matcher(run_id, matcher, expansion_store)
        expansion_store.recompute_touch_counts(run_id)

        unique_new = len(matcher._proposed_by_label)
        stats = {
            "processed": processed,
            "errors": errors,
            "new_kps": unique_new,
            "mapping_new_hits": new_kp_count,
            "matched_catalog": matched_catalog,
            "unmatched_skills": unmatched_count,
            "prompt_version": PROMPT_VERSION,
            "catalog_kp_count": len(catalog.knowledge_points),
        }
        expansion_store.update_run(
            run_id,
            status="completed",
            stats=stats,
            model_label=model_label or None,
            completed=True,
        )
        return stats
    except Exception as exc:
        logger.exception("Gap expansion run %s failed: %s", run_id, exc)
        expansion_store.update_run(
            run_id,
            status="failed",
            error_message=str(exc),
            processed_count=processed,
        )
        raise


def build_expanded_graph_payload(
    baseline_graph: dict[str, Any],
    run_id: int,
    expansion_store: KgExpansionStore,
) -> dict[str, Any]:
    """Merge proposed nodes into baseline graph and attach expansion summary."""
    baseline_nodes = list(baseline_graph.get("nodes") or [])
    baseline_edges = list(baseline_graph.get("edges") or [])
    baseline_ids = {n["knowledge_node_id"] for n in baseline_nodes}

    proposed_nodes = expansion_store.list_proposed_nodes(run_id)
    proposed_kps = expansion_store.list_proposed_kps(run_id)
    proposed_ids = {pn["knowledge_node_id"] for pn in proposed_nodes}
    valid_prereq_ids = baseline_ids | proposed_ids

    expanded_nodes = list(baseline_nodes)
    expanded_edges = list(baseline_edges)
    added_nodes: list[dict[str, Any]] = []

    max_depth = int((baseline_graph.get("stats") or {}).get("max_depth") or 0)

    for pn in proposed_nodes:
        nid = pn["knowledge_node_id"]
        if nid in baseline_ids:
            continue
        prereqs = [
            p
            for p in (pn.get("prerequisites") or [])
            if p in valid_prereq_ids and p != nid
        ]
        depth = 0
        if prereqs:
            prereq_depths = []
            for p in prereqs:
                base = next(
                    (n for n in baseline_nodes if n["knowledge_node_id"] == p),
                    None,
                )
                if base:
                    prereq_depths.append(int(base.get("depth_level") or 0))
            if prereq_depths:
                depth = 1 + max(prereq_depths)
        max_depth = max(max_depth, depth)
        entry: dict[str, Any] = {
            "knowledge_node_id": nid,
            "label": pn.get("label", ""),
            "description": pn.get("description", ""),
            "prerequisites": prereqs,
            "depth_level": depth,
            "origin": "proposed",
            "touch_count": int(pn.get("touch_count") or 0),
            "proposed_kp_id": pn.get("proposed_kp_id"),
            "run_id": run_id,
        }
        expanded_nodes.append(entry)
        added_nodes.append(
            {
                "knowledge_node_id": nid,
                "label": entry["label"],
                "touch_count": entry["touch_count"],
                "proposed_kp_id": pn.get("proposed_kp_id"),
            }
        )
        for prereq in prereqs:
            if prereq != nid:
                expanded_edges.append({"source": prereq, "target": nid})

    unmatched_touches: dict[str, dict] = {}
    matched_touches: dict[str, dict] = {}
    for q in expansion_store.list_questions(run_id):
        seen_unmatched: set[str] = set()
        seen_matched: set[str] = set()
        for m in q.get("mappings") or []:
            mt = m.get("match_type")
            if mt == "unmatched":
                key = (m.get("normalized_statement") or "").strip().lower()
                if not key or key in seen_unmatched:
                    continue
                seen_unmatched.add(key)
                row = unmatched_touches.setdefault(
                    key,
                    {
                        "normalized_statement": m.get("normalized_statement"),
                        "touch_count": 0,
                        "best_similarity": m.get("similarity", 0),
                    },
                )
                row["touch_count"] += 1
                row["best_similarity"] = max(
                    row["best_similarity"], m.get("similarity", 0) or 0
                )
            elif mt == "existing_catalog":
                kp_id = m.get("source_kp_id") or ""
                if not kp_id or kp_id in seen_matched:
                    continue
                seen_matched.add(kp_id)
                row = matched_touches.setdefault(
                    kp_id,
                    {
                        "source_kp_id": kp_id,
                        "label": m.get("label"),
                        "knowledge_node_id": m.get("knowledge_node_id"),
                        "touch_count": 0,
                    },
                )
                row["touch_count"] += 1

    unmatched_summary = sorted(
        unmatched_touches.values(),
        key=lambda x: (-x["touch_count"], x.get("normalized_statement") or ""),
    )
    matched_summary = sorted(
        matched_touches.values(),
        key=lambda x: (-x["touch_count"], x.get("label") or ""),
    )

    depth_counts = dict((baseline_graph.get("stats") or {}).get("depth_counts") or {})
    for n in expanded_nodes:
        if n.get("origin") == "proposed":
            key = str(n.get("depth_level", 0))
            depth_counts[key] = depth_counts.get(key, 0) + 1

    return {
        **baseline_graph,
        "nodes": expanded_nodes,
        "edges": expanded_edges,
        "stats": {
            **(baseline_graph.get("stats") or {}),
            "node_count": len(expanded_nodes),
            "edge_count": len(expanded_edges),
            "max_depth": max_depth,
            "depth_counts": depth_counts,
            "proposed_node_count": len(added_nodes),
        },
        "expansion": {
            "run_id": run_id,
            "proposed_kps": proposed_kps,
            "proposed_nodes": proposed_nodes,
            "unmatched_skills": unmatched_summary,
            "matched_catalog_kps": matched_summary,
            "unmatched_skill_count": len(unmatched_summary),
            "matched_catalog_count": len(matched_summary),
            "diff": {
                "baseline_node_count": len(baseline_nodes),
                "expanded_node_count": len(expanded_nodes),
                "added_node_count": len(added_nodes),
                "added_nodes": added_nodes,
                "unchanged_node_ids": sorted(baseline_ids),
            },
        },
    }


def build_run_analysis(
    baseline_graph: dict[str, Any],
    run_id: int,
    expansion_store: KgExpansionStore,
) -> dict[str, Any]:
    return build_expanded_graph_payload(baseline_graph, run_id, expansion_store)
