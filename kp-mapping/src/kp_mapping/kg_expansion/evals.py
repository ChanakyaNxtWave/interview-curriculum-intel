"""Offline eval helpers for gap-expansion KP proposals."""

from __future__ import annotations

import re

from .fewshot import load_eval_seed_rows
from .matcher import is_catalog_kp_id, label_similarity


def _normalize_labels(labels: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", (x or "").lower().strip()) for x in labels if x]


def _catalog_ids_from_row(row: dict, key: str = "gold_catalog_matches") -> list[str]:
    out: list[str] = []
    for item in row.get(key) or []:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict):
            kid = str(item.get("source_kp_id") or "").strip()
            if kid:
                out.append(kid)
    return out


def validate_gold_prerequisites(row: dict) -> dict:
    """Check eval seed rows include prerequisite_skill_ids where required."""
    entry_level = bool(row.get("entry_level"))
    gold_new = row.get("gold_new_kps") or []
    issues: list[str] = []

    for i, kp in enumerate(gold_new):
        if not isinstance(kp, dict):
            issues.append(f"gold_new_kps[{i}] not an object")
            continue
        prereqs = kp.get("prerequisite_skill_ids")
        if prereqs is None:
            issues.append(f"gold_new_kps[{i}] missing prerequisite_skill_ids")
            continue
        if not isinstance(prereqs, list):
            issues.append(f"gold_new_kps[{i}] prerequisite_skill_ids must be a list")
            continue
        if not prereqs and not entry_level:
            issues.append(f"gold_new_kps[{i}] empty prerequisite_skill_ids")
        for pid in prereqs:
            if not is_catalog_kp_id(str(pid)) and not re.match(r"^s\d+$", str(pid)):
                issues.append(
                    f"gold_new_kps[{i}] invalid prerequisite_skill_id: {pid!r}"
                )

    row_prereqs = row.get("gold_prerequisite_skill_ids")
    if row_prereqs is None and not entry_level and not gold_new:
        issues.append("missing gold_prerequisite_skill_ids for catalog-only row")

    return {
        "row_key": row.get("row_key"),
        "valid": len(issues) == 0,
        "issues": issues,
    }


def score_prerequisite_skill_ids(
    predicted: list[str],
    gold: list[str],
) -> dict:
    """Recall on catalog KP ids in prerequisite_skill_ids."""
    pred_catalog = [p for p in predicted if is_catalog_kp_id(p)]
    gold_catalog = [g for g in gold if is_catalog_kp_id(g)]
    if not gold_catalog:
        return {"recall": 1.0, "matched": 0, "gold_count": 0, "pred_count": len(pred_catalog)}
    matched = sum(1 for g in gold_catalog if g in pred_catalog)
    return {
        "recall": round(matched / len(gold_catalog), 4),
        "matched": matched,
        "gold_count": len(gold_catalog),
        "pred_count": len(pred_catalog),
    }


def score_proposed_kp_labels(
    predicted_labels: list[str],
    gold_labels: list[str],
    *,
    match_threshold: float = 0.82,
) -> dict:
    pred = _normalize_labels(predicted_labels)
    gold = _normalize_labels(gold_labels)
    if not gold and not pred:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matched_gold": 0, "matched_pred": 0}
    matched_gold = 0
    used_pred: set[int] = set()
    for g in gold:
        best_i = -1
        best_score = 0.0
        for i, p in enumerate(pred):
            if i in used_pred:
                continue
            score = label_similarity(g, p)
            if score > best_score:
                best_score = score
                best_i = i
        if best_i >= 0 and best_score >= match_threshold:
            matched_gold += 1
            used_pred.add(best_i)
    matched_pred = len(used_pred)
    precision = matched_pred / len(pred) if pred else (1.0 if not gold else 0.0)
    recall = matched_gold / len(gold) if gold else (1.0 if not pred else 0.0)
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matched_gold": matched_gold,
        "matched_pred": matched_pred,
        "gold_count": len(gold),
        "pred_count": len(pred),
    }


def over_granular_penalty(predicted_labels: list[str], bad_labels: list[str]) -> float:
    if not predicted_labels or not bad_labels:
        return 0.0
    hits = 0
    for p in predicted_labels:
        for b in bad_labels:
            if label_similarity(p, b) >= 0.75:
                hits += 1
                break
    return round(hits / len(predicted_labels), 4)


def prereq_dump_penalty(prereq_count: int, *, max_ok: int = 5) -> float:
    if prereq_count <= max_ok:
        return 0.0
    return round(min(1.0, (prereq_count - max_ok) / max(prereq_count, 1)), 4)


def missing_prereq_penalty(
    predicted_new_kps: list[dict],
    *,
    entry_level: bool = False,
) -> float:
    if entry_level:
        return 0.0
    if not predicted_new_kps:
        return 0.0
    missing = 0
    for kp in predicted_new_kps:
        prereqs = kp.get("prerequisite_skill_ids")
        if not prereqs:
            missing += 1
    return round(missing / len(predicted_new_kps), 4)


def evaluate_seed_row(
    row: dict,
    *,
    predicted_new_kps: list[dict] | None = None,
    predicted_catalog_ids: list[str] | None = None,
    predicted_question_prereqs: list[str] | None = None,
) -> dict:
    gold_new = row.get("gold_new_kps") or []
    gold_labels = [k.get("label", "") for k in gold_new if isinstance(k, dict)]
    gold_catalog = _catalog_ids_from_row(row)
    bad_granular = [k.get("label", "") for k in (row.get("bad_new_kps_over_granular") or [])]

    pred_kps = predicted_new_kps or []
    pred_labels = [str(k.get("label", "")) for k in pred_kps if isinstance(k, dict)]
    pred_prereq_union: list[str] = list(predicted_question_prereqs or [])
    for kp in pred_kps:
        if isinstance(kp, dict):
            pred_prereq_union.extend(kp.get("prerequisite_skill_ids") or [])

    gold_prereq_union = list(row.get("gold_prerequisite_skill_ids") or [])
    for kp in gold_new:
        if isinstance(kp, dict):
            gold_prereq_union.extend(kp.get("prerequisite_skill_ids") or [])

    label_scores = score_proposed_kp_labels(pred_labels, gold_labels)
    catalog_ids = predicted_catalog_ids or []
    catalog_recall = (
        sum(1 for g in gold_catalog if g in catalog_ids) / len(gold_catalog)
        if gold_catalog
        else (1.0 if not catalog_ids else 0.0)
    )

    max_prereq_nodes = max(
        (len(k.get("prerequisite_skill_ids") or []) for k in pred_kps if isinstance(k, dict)),
        default=0,
    )

    return {
        "row_key": row.get("row_key"),
        "gold_validation": validate_gold_prerequisites(row),
        "label_scores": label_scores,
        "prerequisite_scores": score_prerequisite_skill_ids(
            pred_prereq_union, gold_prereq_union
        ),
        "catalog_recall": round(catalog_recall, 4),
        "over_granular_penalty": over_granular_penalty(pred_labels, bad_granular),
        "prereq_dump_penalty": prereq_dump_penalty(max_prereq_nodes),
        "missing_prereq_penalty": missing_prereq_penalty(
            pred_kps, entry_level=bool(row.get("entry_level"))
        ),
    }


def run_eval_seed_report(rows: list[dict] | None = None) -> dict:
    seed = rows if rows is not None else load_eval_seed_rows()
    validations = [validate_gold_prerequisites(r) for r in seed]
    invalid = [v for v in validations if not v["valid"]]
    return {
        "eval_seed_count": len(seed),
        "gold_valid_count": sum(1 for v in validations if v["valid"]),
        "gold_invalid": invalid,
        "rows": [
            {
                "row_key": r.get("row_key"),
                "gold_new_kp_count": len(r.get("gold_new_kps") or []),
                "gold_catalog_count": len(_catalog_ids_from_row(r)),
                "gold_prerequisite_skill_ids": r.get("gold_prerequisite_skill_ids"),
                "notes": r.get("notes"),
            }
            for r in seed
        ],
    }
