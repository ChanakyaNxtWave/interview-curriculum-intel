from __future__ import annotations

from typing import List

from pydantic import BaseModel


class KnowledgeNode(BaseModel):
    knowledge_node_id: str
    label: str
    description: str
    prerequisites: List[str]
    depth_level: int


class AgentResult(BaseModel):
    question: str
    coverage_status: str          # "full" | "partial" | "none"
    existing_node_ids: List[str]  # topologically ordered prerequisite closure
    new_nodes: List[KnowledgeNode]
    reasoning: str


class QuestionInput(BaseModel):
    question: str
    solution: str = ""
