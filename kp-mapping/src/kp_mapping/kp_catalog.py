from __future__ import annotations

import json
from pathlib import Path

from .models import KPCatalog, KnowledgePoint


def load_catalog(path: Path) -> KPCatalog:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return KPCatalog.model_validate(data)


def catalog_prompt_block(catalog: KPCatalog, max_kps: int | None = None) -> str:
    """Compact KP list for LLM prompts."""
    kps = catalog.knowledge_points
    if max_kps:
        kps = kps[:max_kps]
    lines = []
    for kp in kps:
        lines.append(
            f"- {kp.source_kp_id} | {kp.label} ({kp.label_enum}): {kp.description[:200]}"
        )
    return "\n".join(lines)


def kp_lookup(catalog: KPCatalog) -> dict[str, KnowledgePoint]:
    return {kp.source_kp_id: kp for kp in catalog.knowledge_points}


def validate_kp_ids(catalog: KPCatalog, ids: list[str]) -> tuple[list[str], list[str]]:
    known = kp_lookup(catalog)
    valid = [i for i in ids if i in known]
    invalid = [i for i in ids if i not in known]
    return valid, invalid
