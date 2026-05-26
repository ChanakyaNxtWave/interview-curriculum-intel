from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

from .models import ContentPiece

_RM_LIST_FILENAME = "rm_list.json"

_SUFFIX_MAP = {
    "_reading_material.json": "reading_material",
    "_coding.json": "coding_question",
    "_project.json": "project",
    "_assessment.json": "assessment",
    "_quiz.json": "quiz",
    "_tutorial.json": "tutorial",
}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _infer_content_type(path: Path) -> str:
    name = path.name
    for suffix, ctype in _SUFFIX_MAP.items():
        if name.endswith(suffix):
            return ctype
    return "other"


def _content_id(data: dict, path: Path) -> str:
    for key in ("question_id", "learning_resource_id", "content_id", "project_id"):
        if data.get(key):
            return str(data[key])
    return path.stem


def _title(data: dict, path: Path) -> str:
    for key in ("short_text", "unit_title", "title", "project_title"):
        if data.get(key):
            return str(data[key]).strip()
    return path.stem


def _body(data: dict) -> str:
    for key in ("content", "body", "description"):
        if data.get(key):
            raw = str(data[key])
            if "<" in raw and ">" in raw:
                return _strip_html(raw)
            return raw.strip()
    return ""


def _extract_solution(data: dict, content_type: str) -> tuple[str | None, str | None, bool]:
    """
    For coding/project: only use explicit solution code from JSON.
    Returns (solution_text, solution_source, solution_missing).
    """
    if content_type not in ("coding_question", "project"):
        return None, None, False

    codes = data.get("codes") or []
    if not codes:
        return None, None, True

    default_entries = [c for c in codes if c.get("default_code")]
    if len(default_entries) == 1:
        entry = default_entries[0]
        return (
            str(entry.get("code_content", "")).strip(),
            str(entry.get("code_id", "default_code")),
            False,
        )

    if len(default_entries) > 1:
        # Ambiguous — flag; use first default only for mapping context
        entry = default_entries[0]
        return (
            str(entry.get("code_content", "")).strip(),
            str(entry.get("code_id", "ambiguous_default")),
            True,
        )

    if len(codes) == 1:
        entry = codes[0]
        return (
            str(entry.get("code_content", "")).strip(),
            str(entry.get("code_id", "single_code")),
            True,  # no explicit default — human should confirm
        )

    # Multiple codes, no default
    return None, None, True


def load_rm_list(curriculum_root: Path) -> dict[str, set[str]]:
    """Load exclusion sets from curriculum/rm_list.json (all keys optional)."""
    path = curriculum_root / _RM_LIST_FILENAME
    empty: dict[str, set[str]] = {
        "excluded_unit_names": set(),
        "excluded_unit_titles": set(),
        "excluded_learning_resource_ids": set(),
        "excluded_content_ids": set(),
    }
    if not path.is_file():
        return empty

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    return {
        key: {str(v).strip() for v in data.get(key, []) if str(v).strip()}
        for key in empty
    }


def is_excluded(piece: ContentPiece, rm: dict[str, set[str]]) -> bool:
    if piece.content_id in rm["excluded_content_ids"]:
        return True
    meta = piece.metadata or {}
    unit_name = meta.get("unit_name") or piece.topic_name or ""
    unit_title = meta.get("unit_title") or piece.title or ""
    if unit_name in rm["excluded_unit_names"]:
        return True
    if unit_title in rm["excluded_unit_titles"]:
        return True
    lr_id = str(meta.get("learning_resource_id") or "")
    if lr_id and lr_id in rm["excluded_learning_resource_ids"]:
        return True
    return False


def load_content_file(path: Path) -> ContentPiece:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    content_type = _infer_content_type(path)
    solution_text, solution_source, solution_missing = _extract_solution(data, content_type)

    return ContentPiece(
        content_id=_content_id(data, path),
        file_path=str(path),
        content_type=content_type,
        title=_title(data, path),
        topic_name=data.get("topic_name"),
        course_title=data.get("course_title"),
        body_text=_body(data),
        solution_text=solution_text,
        solution_source=solution_source,
        solution_missing=solution_missing,
        raw_object_type=data.get("object_type"),
        metadata={
            "question_type": data.get("question_type"),
            "content_type_field": data.get("content_type"),
            "unit_name": data.get("unit_name"),
            "unit_title": data.get("unit_title"),
            "learning_resource_id": data.get("learning_resource_id"),
        },
    )


def discover_content(
    curriculum_root: Path,
    *,
    course_subdir: str | None = "ProgrammingFoundations",
    content_types: set[str] | None = None,
) -> list[ContentPiece]:
    search_root = curriculum_root
    if course_subdir:
        candidate = curriculum_root / course_subdir
        if candidate.is_dir():
            search_root = candidate

    rm = load_rm_list(curriculum_root)
    pieces: list[ContentPiece] = []
    for path in sorted(search_root.rglob("*.json")):
        if path.name.startswith("KPs-") or path.name == _RM_LIST_FILENAME:
            continue
        piece = load_content_file(path)
        if content_types and piece.content_type not in content_types:
            continue
        if is_excluded(piece, rm):
            continue
        pieces.append(piece)
    return pieces
