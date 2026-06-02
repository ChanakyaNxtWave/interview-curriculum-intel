from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import dspy

from .dspy_modules import TheoryPipeline
from .store import TheoryStore


VERDICTS = {"covered", "not_covered"}


def load_seed_into_store(seed_path: Path, store: TheoryStore) -> int:
    """Load seed golds from JSONL idempotently — inserts only row_keys that
    aren't already present. Returns # inserted.
    """
    if not seed_path.exists():
        return 0
    existing_keys = {r.get("row_key") for r in store.list_evals(source="seed")}
    inserted = 0
    with seed_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            verdict = rec["gold_verdict"]
            # Collapse legacy 4-verdict values to binary.
            if verdict in {"partially_covered", "uncertain"}:
                verdict = "not_covered"
            assert verdict in VERDICTS, f"Bad verdict in seed line {i}: {verdict}"
            row_key = rec.get("row_key", f"seed-{i}")
            if row_key in existing_keys:
                continue
            is_holdout = bool(rec.get("is_holdout", False))
            store.insert_eval(
                row_key=row_key,
                question=rec["question"],
                gold_required_kps=rec.get("gold_required_kps", []),
                gold_citations=rec.get("gold_citations", []),
                gold_verdict=verdict,
                gold_rationale=rec.get("gold_rationale", ""),
                source="seed",
                is_holdout=is_holdout,
                added_by="seed_loader",
            )
            inserted += 1
    return inserted


def golds_to_examples(
    golds: list[dict],
    *,
    kp_catalog_text: str,
    citations_for: Callable[[list[str]], list[dict]],
) -> list[dspy.Example]:
    """Build DSPy training examples; replicate each by `feedback_weight` (1-3).

    Replication is the standard low-friction way to upweight examples in
    BootstrapFewShot — high-severity reviewer feedback gets 3x exposure.
    """
    examples: list[dspy.Example] = []
    for g in golds:
        req_kps = g.get("gold_required_kps", [])
        kp_ids = [k.get("source_kp_id") for k in req_kps if k.get("source_kp_id")]
        candidates = citations_for(kp_ids) if kp_ids else []
        ex = dspy.Example(
            question=g["question"],
            kp_catalog=kp_catalog_text,
            citations_for=citations_for,
            required_kps=req_kps,
            candidate_citations=candidates,
            accepted_citations=g.get("gold_citations", []),
            verdict=g["gold_verdict"],
            rationale=g.get("gold_rationale", ""),
            overall_confidence=1.0,
        ).with_inputs("question", "kp_catalog", "citations_for")
        weight = max(1, min(3, int(g.get("feedback_weight", 1) or 1)))
        for _ in range(weight):
            examples.append(ex)
    return examples


def kp_set(kps: list[dict]) -> set[str]:
    return {str(k.get("source_kp_id", "")).strip() for k in kps if k.get("source_kp_id")}


def verdict_match_metric(example, prediction, trace=None) -> float:
    """Composite metric: verdict match + KP set Jaccard + consistency check.

    Binary verdict system: only covered | not_covered.

    Returns 0.0 (hard reject) for:
      • verdict='covered' with no accepted_citations
      • verdict mismatch with gold

    Otherwise:
      1.0 if KP Jaccard >= 0.5
      0.5 if KP Jaccard low
    """
    pred_verdict = getattr(prediction, "verdict", "not_covered")
    pred_accepted = list(getattr(prediction, "accepted_citations", []) or [])

    # Consistency penalty: covered without citations is invalid.
    if pred_verdict == "covered" and not pred_accepted:
        return 0.0

    if pred_verdict != example.verdict:
        return 0.0
    pred_kps = kp_set(getattr(prediction, "required_kps", []) or [])
    gold_kps = kp_set(example.required_kps or [])
    if not gold_kps and not pred_kps:
        return 1.0
    if not gold_kps or not pred_kps:
        return 0.5
    inter = len(pred_kps & gold_kps)
    union = len(pred_kps | gold_kps)
    jacc = inter / union if union else 0.0
    return 1.0 if jacc >= 0.5 else 0.5


def _safe_conf(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def evaluate_pipeline(
    pipeline: TheoryPipeline,
    devset: list[dspy.Example],
) -> dict:
    """Run pipeline over devset and return aggregate metrics."""
    total = 0
    verdict_agree = 0
    false_covered = 0
    false_not_covered = 0
    jaccards: list[float] = []
    confidences: list[float] = []
    for ex in devset:
        try:
            pred = pipeline(
                question=ex.question,
                kp_catalog=ex.kp_catalog,
                citations_for=ex.citations_for,
            )
        except Exception:
            total += 1
            continue
        total += 1
        if pred.verdict == ex.verdict:
            verdict_agree += 1
        else:
            if pred.verdict == "covered" and ex.verdict == "not_covered":
                false_covered += 1
            if pred.verdict == "not_covered" and ex.verdict == "covered":
                false_not_covered += 1
        pred_kps = kp_set(getattr(pred, "required_kps", []) or [])
        gold_kps = kp_set(ex.required_kps or [])
        if pred_kps or gold_kps:
            inter = len(pred_kps & gold_kps)
            union = len(pred_kps | gold_kps)
            jaccards.append(inter / union if union else 0.0)
        confidences.append(float(getattr(pred, "overall_confidence", 0.0)))

    agreement_rate = verdict_agree / total if total else 0.0
    return {
        "total": total,
        "verdict_agree": verdict_agree,
        "false_covered": false_covered,
        "false_not_covered": false_not_covered,
        "kp_jaccard_avg": sum(jaccards) / len(jaccards) if jaccards else 0.0,
        "avg_confidence": sum(confidences) / len(confidences) if confidences else 0.0,
        "agreement_rate": agreement_rate,
    }
