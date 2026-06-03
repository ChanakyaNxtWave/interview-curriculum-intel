from __future__ import annotations

import re
import uuid
from difflib import SequenceMatcher

from ..models import KPCatalog, KnowledgePoint

CATALOG_KP_ID_RE = re.compile(r"^KP_GLOBAL_\d+$", re.IGNORECASE)


def is_catalog_kp_id(value: str) -> bool:
    return bool(CATALOG_KP_ID_RE.match((value or "").strip()))


def _normalize_label(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def label_similarity(a: str, b: str) -> float:
    na, nb = _normalize_label(a), _normalize_label(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    return SequenceMatcher(None, na, nb).ratio()


def _new_proposed_ids() -> tuple[str, str]:
    node_id = str(uuid.uuid4())
    proposed_kp_id = f"PROP_{node_id[:8].upper()}"
    return proposed_kp_id, node_id


class KpMatcher:
    """Match skills to catalog KPs and deduplicate proposed KPs within a run."""

    def __init__(
        self,
        catalog: KPCatalog,
        *,
        match_threshold: float = 0.82,
        proposed_match_threshold: float = 0.88,
    ) -> None:
        self.match_threshold = match_threshold
        self.proposed_match_threshold = proposed_match_threshold
        self._catalog_entries: list[tuple[str, str, KnowledgePoint]] = [
            (kp.source_kp_id, kp.label, kp) for kp in catalog.knowledge_points
        ]
        self._catalog_by_id: dict[str, KnowledgePoint] = {
            kp.source_kp_id: kp for kp in catalog.knowledge_points
        }
        self._proposed_by_label: dict[str, dict] = {}

    def catalog_prompt_excerpt(self, *, limit: int = 120) -> str:
        lines: list[str] = []
        for kp_id, label, kp in self._catalog_entries[:limit]:
            desc = (kp.description or "")[:200]
            lines.append(f"{kp_id} | {label} | {desc}")
        return "\n".join(lines)

    def match_catalog(self, normalized_statement: str) -> dict:
        best_score = 0.0
        best_catalog: KnowledgePoint | None = None

        for _kp_id, label, kp in self._catalog_entries:
            score = label_similarity(normalized_statement, label)
            if score > best_score:
                best_score = score
                best_catalog = kp

        if best_score >= self.match_threshold and best_catalog is not None:
            return {
                "match_type": "existing_catalog",
                "similarity": round(best_score, 4),
                "source_kp_id": best_catalog.source_kp_id,
                "knowledge_node_id": best_catalog.knowledge_node_id,
                "label": best_catalog.label,
            }

        return {
            "match_type": "unmatched",
            "similarity": round(best_score, 4),
            "normalized_statement": normalized_statement,
        }

    def match_proposed(self, label: str) -> dict | None:
        key = _normalize_label(label)
        if not key:
            return None
        for norm, entry in self._proposed_by_label.items():
            if label_similarity(key, norm) >= self.proposed_match_threshold:
                return {
                    "match_type": "existing_proposed",
                    "similarity": round(label_similarity(key, norm), 4),
                    "proposed_kp_id": entry["proposed_kp_id"],
                    "knowledge_node_id": entry["knowledge_node_id"],
                    "label": entry["label"],
                    "description": entry["description"],
                    "prerequisites": list(entry.get("prerequisites") or []),
                }
        return None

    def register_proposed(
        self,
        *,
        label: str,
        description: str,
        prerequisites: list[str],
    ) -> dict:
        existing = self.match_proposed(label)
        if existing:
            return existing

        proposed_kp_id, knowledge_node_id = _new_proposed_ids()
        entry = {
            "proposed_kp_id": proposed_kp_id,
            "knowledge_node_id": knowledge_node_id,
            "label": label.strip(),
            "description": (description or "").strip(),
            "prerequisites": prerequisites,
        }
        self._proposed_by_label[_normalize_label(label)] = entry
        return {
            "match_type": "new",
            "similarity": 1.0,
            **entry,
        }

    def resolve_catalog_ids(self, source_kp_ids: list[str]) -> list[str]:
        """Map catalog source_kp_id values to knowledge_node_ids for graph edges."""
        out: list[str] = []
        for kp_id in source_kp_ids:
            kid = (kp_id or "").strip()
            if not is_catalog_kp_id(kid):
                continue
            kp = self._catalog_by_id.get(kid)
            if kp and kp.knowledge_node_id and kp.knowledge_node_id not in out:
                out.append(kp.knowledge_node_id)
        return out

    def split_prerequisite_skill_ids(
        self,
        prereq_ids: list[str],
        *,
        skill_nodes: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        """Return (lta_skill_ids, catalog_kp_ids) from mixed prerequisite_skill_ids."""
        lta: list[str] = []
        catalog: list[str] = []
        for raw in prereq_ids:
            sid = str(raw).strip()
            if not sid:
                continue
            if is_catalog_kp_id(sid):
                if sid not in catalog:
                    catalog.append(sid)
            elif sid in skill_nodes:
                lta.append(sid)
        return lta, catalog
