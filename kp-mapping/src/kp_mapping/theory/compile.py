from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

import dspy
from dspy.teleprompt import BootstrapFewShot

from ..kp_catalog import KPCatalog
from .dspy_modules import TheoryPipeline, configure_lm, kp_catalog_prompt
from .evals import (
    evaluate_pipeline,
    golds_to_examples,
    load_seed_into_store,
    verdict_match_metric,
)
from .store import TheoryStore

logger = logging.getLogger("kp_mapping.theory.compile")


COMPILE_THRESHOLD = int(os.environ.get("THEORY_COMPILE_THRESHOLD", "20"))
DEV_AGREEMENT_GATE = float(os.environ.get("THEORY_DEV_AGREEMENT_GATE", "0.85"))


def _next_version_name(store: TheoryStore) -> str:
    versions = store.list_prompt_versions()
    return f"theory-v{len(versions) + 1}-bootstrap"


def compile_and_maybe_activate(
    *,
    store: TheoryStore,
    catalog: KPCatalog,
    citations_for: Callable[[list[str]], list[dict]],
    trigger: str,
    max_bootstrapped_demos: int = 4,
    force_activate: bool = False,
) -> dict:
    configure_lm()
    catalog_text = kp_catalog_prompt(catalog)

    train_rows = store.list_evals(is_holdout=False)
    dev_rows = store.list_evals(is_holdout=True)

    if not train_rows:
        raise RuntimeError("No training golds available; load seed first")

    trainset = golds_to_examples(
        train_rows, kp_catalog_text=catalog_text, citations_for=citations_for
    )
    devset = golds_to_examples(
        dev_rows, kp_catalog_text=catalog_text, citations_for=citations_for
    )

    base = TheoryPipeline()
    optimizer = BootstrapFewShot(
        metric=verdict_match_metric,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_bootstrapped_demos,
    )
    compiled = optimizer.compile(base, trainset=trainset)

    eval_target = devset if devset else trainset
    metrics = evaluate_pipeline(compiled, eval_target)
    devset_agreement = metrics["agreement_rate"]
    activate = force_activate or devset_agreement >= DEV_AGREEMENT_GATE

    state = compiled.dump_state()
    version = _next_version_name(store)
    if activate:
        store.insert_prompt_version(
            version=version,
            compiled_json=json.dumps(state, default=str),
            fewshot_count=max_bootstrapped_demos,
            gold_count_at_compile=len(train_rows),
            devset_agreement=devset_agreement,
            notes=f"trigger={trigger}; activated",
            activate=True,
        )
        active_version = version
    else:
        # Log a version row but do NOT activate it.
        store.insert_prompt_version(
            version=version,
            compiled_json=json.dumps(state, default=str),
            fewshot_count=max_bootstrapped_demos,
            gold_count_at_compile=len(train_rows),
            devset_agreement=devset_agreement,
            notes=f"trigger={trigger}; below gate, not activated",
            activate=False,
        )
        active = store.get_active_prompt_version()
        active_version = active["version"] if active else version

    store.insert_eval_run(
        prompt_version=version,
        model=os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5"),
        trigger=f"{trigger}:compile",
        total=metrics["total"],
        verdict_agree=metrics["verdict_agree"],
        false_covered=metrics["false_covered"],
        false_not_covered=metrics["false_not_covered"],
        kp_jaccard_avg=metrics["kp_jaccard_avg"],
        avg_confidence=metrics["avg_confidence"],
        agreement_rate=devset_agreement,
    )

    return {
        "version": version,
        "activated": activate,
        "active_version": active_version,
        "devset_agreement": devset_agreement,
        "metrics": metrics,
        "trainset_size": len(trainset),
        "devset_size": len(devset),
    }


def cold_start_if_needed(
    *,
    seed_path: Path,
    store: TheoryStore,
    catalog: KPCatalog,
    citations_for: Callable[[list[str]], list[dict]],
) -> dict | None:
    """Load seeds + force-compile theory-v1-bootstrap if no active version yet."""
    inserted = load_seed_into_store(seed_path, store)
    if store.get_active_prompt_version():
        return {"seed_inserted": inserted, "compile_skipped": True}
    try:
        result = compile_and_maybe_activate(
            store=store,
            catalog=catalog,
            citations_for=citations_for,
            trigger="cold_start",
            force_activate=True,
        )
    except Exception as exc:
        logger.exception("Cold-start compile failed: %s", exc)
        return {"seed_inserted": inserted, "compile_error": str(exc)}
    return {"seed_inserted": inserted, **result}


def check_compile_trigger(
    *,
    store: TheoryStore,
    catalog: KPCatalog,
    citations_for: Callable[[list[str]], list[dict]],
    threshold: int = COMPILE_THRESHOLD,
) -> dict | None:
    """If enough new golds accumulated since last compile, run compile."""
    last = store.last_compile_at()
    new_count = store.count_evals_since(last)
    if new_count < threshold:
        return None
    return compile_and_maybe_activate(
        store=store,
        catalog=catalog,
        citations_for=citations_for,
        trigger="auto_threshold",
    )


def load_active_pipeline(store: TheoryStore) -> tuple[TheoryPipeline, str]:
    """Construct a TheoryPipeline and load the active compiled state into it.

    Returns (pipeline, version).
    """
    configure_lm()
    pipeline = TheoryPipeline()
    active = store.get_active_prompt_version()
    if not active:
        return pipeline, ""
    try:
        state = json.loads(active["compiled_json"])
        pipeline.load_state(state)
    except Exception as exc:
        logger.warning("Failed to load active compiled state: %s", exc)
    return pipeline, active["version"]
