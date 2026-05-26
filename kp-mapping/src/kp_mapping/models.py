from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class TagRole(str, Enum):
    EXPLAIN = "explain"
    PRACTICE = "practice"
    EXAMPLE = "example"
    ASSESSMENT = "assessment"
    PROJECT = "project"
    SYNTAX = "syntax"
    PREREQUISITE = "prerequisite"


class KnowledgePoint(BaseModel):
    source_kp_id: str
    knowledge_node_id: str
    label: str
    label_enum: str
    description: str


class KPCatalog(BaseModel):
    catalog_id: str
    source_file: str
    count: int
    knowledge_points: list[KnowledgePoint]


class ContentPiece(BaseModel):
    content_id: str
    file_path: str
    content_type: str  # reading_material | coding_question | project | other
    title: str
    topic_name: str | None = None
    course_title: str | None = None
    body_text: str
    solution_text: str | None = None
    solution_source: str | None = None  # e.g. code_id or path
    solution_missing: bool = False
    raw_object_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposedKPTag(BaseModel):
    source_kp_id: str
    label: str
    tag_role: TagRole = TagRole.PRACTICE
    confidence: ConfidenceLevel
    rationale: str = ""


class MappingResult(BaseModel):
    content_id: str
    proposed_tags: list[ProposedKPTag]
    overall_confidence: ConfidenceLevel
    needs_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_version: str = "kp-map-v1"


class StoredMapping(BaseModel):
    id: int | None = None
    content_id: str
    file_path: str
    content_type: str
    title: str
    topic_name: str | None = None
    course_title: str | None = None
    ai_result: MappingResult
    human_tags: list[ProposedKPTag] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewer_notes: str = ""
    updated_at: str | None = None
