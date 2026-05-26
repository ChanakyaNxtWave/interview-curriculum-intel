from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    MappingResult,
    ProposedKPTag,
    ReviewStatus,
    StoredMapping,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MappingStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    topic_name TEXT,
                    course_title TEXT,
                    ai_result_json TEXT NOT NULL,
                    human_tags_json TEXT NOT NULL DEFAULT '[]',
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    reviewer_notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_review_status
                    ON content_mappings(review_status);
                CREATE INDEX IF NOT EXISTS idx_needs_review
                    ON content_mappings(
                        json_extract(ai_result_json, '$.needs_human_review')
                    );
                """
            )

    def upsert_mapping(
        self,
        *,
        content_id: str,
        file_path: str,
        content_type: str,
        title: str,
        topic_name: str | None,
        course_title: str | None,
        ai_result: MappingResult,
    ) -> StoredMapping:
        now = _utc_now()
        payload = ai_result.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO content_mappings (
                    content_id, file_path, content_type, title,
                    topic_name, course_title, ai_result_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_id) DO UPDATE SET
                    file_path = excluded.file_path,
                    content_type = excluded.content_type,
                    title = excluded.title,
                    topic_name = excluded.topic_name,
                    course_title = excluded.course_title,
                    ai_result_json = excluded.ai_result_json,
                    updated_at = excluded.updated_at
                """,
                (
                    content_id,
                    file_path,
                    content_type,
                    title,
                    topic_name,
                    course_title,
                    json.dumps(payload),
                    now,
                ),
            )
        row = self.get_by_content_id(content_id)
        assert row is not None
        return row

    def get_by_content_id(self, content_id: str) -> StoredMapping | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM content_mappings WHERE content_id = ?",
                (content_id,),
            ).fetchone()
        return self._row_to_model(row) if row else None

    def get_review_status_map(
        self, *, content_type: str | None = None
    ) -> dict[str, ReviewStatus]:
        """content_id -> review_status for all stored mappings."""
        clauses: list[str] = []
        params: list[object] = []
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT content_id, review_status FROM content_mappings {where}",
                params,
            ).fetchall()
        result: dict[str, ReviewStatus] = {}
        for row in rows:
            try:
                result[row["content_id"]] = ReviewStatus(row["review_status"])
            except ValueError:
                result[row["content_id"]] = ReviewStatus.PENDING
        return result

    def list_mappings(
        self,
        *,
        review_status: ReviewStatus | None = None,
        needs_human_review: bool | None = None,
        content_type: str | None = None,
        topic_name: str | None = None,
        kp_id: str | None = None,
        confidence: str | None = None,
        has_tags: bool | None = None,
        q: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[StoredMapping]:
        clauses: list[str] = []
        params: list[object] = []

        if review_status:
            clauses.append("review_status = ?")
            params.append(review_status.value)
        if needs_human_review is not None:
            clauses.append(
                "json_extract(ai_result_json, '$.needs_human_review') = ?"
            )
            params.append(1 if needs_human_review else 0)
        if content_type:
            clauses.append("content_type = ?")
            params.append(content_type)
        if topic_name:
            clauses.append("topic_name = ?")
            params.append(topic_name)
        if kp_id:
            needle = f'%"{kp_id}"%'
            clauses.append(
                "(human_tags_json LIKE ? OR ai_result_json LIKE ?)"
            )
            params.extend([needle, needle])
        if confidence:
            clauses.append(
                "json_extract(ai_result_json, '$.overall_confidence') = ?"
            )
            params.append(confidence)
        if has_tags is True:
            clauses.append(
                "("
                "json_array_length(json_extract(ai_result_json, '$.proposed_tags')) > 0"
                " OR json_array_length(human_tags_json) > 0"
                ")"
            )
        elif has_tags is False:
            clauses.append(
                "("
                "COALESCE(json_array_length(json_extract(ai_result_json, '$.proposed_tags')), 0) = 0"
                " AND COALESCE(json_array_length(human_tags_json), 0) = 0"
                ")"
            )
        if q:
            pattern = f"%{q}%"
            clauses.append(
                "(title LIKE ? OR topic_name LIKE ? OR content_id LIKE ?)"
            )
            params.extend([pattern, pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM content_mappings
                {where}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def course_summary(self) -> list[dict]:
        """DISTINCT course_title rows with mapped count."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    course_title,
                    COUNT(*) AS mapped_count
                FROM content_mappings
                WHERE course_title IS NOT NULL AND course_title != ''
                GROUP BY course_title
                ORDER BY course_title
                """
            ).fetchall()
        return [
            {"course_title": r["course_title"], "mapped_count": r["mapped_count"]}
            for r in rows
        ]

    def kp_mapped_counts(
        self, *, course_title: str | None = None
    ) -> dict[str, dict]:
        """Per-KP mapped content count + tag_role breakdown across AI + human tags.

        Returns {source_kp_id: {"count": int, "tag_role_breakdown": {role: n}}}.
        Counts each content piece at most once per (kp_id, tag_role) — tags
        from AI and human overrides are unioned.
        """
        clauses: list[str] = []
        params: list[object] = []
        if course_title:
            clauses.append("course_title = ?")
            params.append(course_title)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT content_id, ai_result_json, human_tags_json
                FROM content_mappings
                {where}
                """,
                params,
            ).fetchall()

        result: dict[str, dict] = {}
        for row in rows:
            content_id = row["content_id"]
            # Union tags from both AI and human, dedup by (kp_id, role) for this content
            tags_for_content: set[tuple[str, str]] = set()
            try:
                ai = json.loads(row["ai_result_json"] or "{}") or {}
                for t in ai.get("proposed_tags", []) or []:
                    kp = (t or {}).get("source_kp_id")
                    role = (t or {}).get("tag_role") or "explain"
                    if kp:
                        tags_for_content.add((kp, role))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            try:
                human = json.loads(row["human_tags_json"] or "[]") or []
                for t in human:
                    kp = (t or {}).get("source_kp_id")
                    role = (t or {}).get("tag_role") or "explain"
                    if kp:
                        tags_for_content.add((kp, role))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

            seen_kp_for_content: set[str] = set()
            for kp, role in tags_for_content:
                entry = result.setdefault(
                    kp, {"count": 0, "tag_role_breakdown": {}}
                )
                if kp not in seen_kp_for_content:
                    entry["count"] += 1
                    seen_kp_for_content.add(kp)
                entry["tag_role_breakdown"][role] = (
                    entry["tag_role_breakdown"].get(role, 0) + 1
                )
        return result

    def filter_facets(self) -> dict[str, list[str]]:
        """Distinct values for filter dropdowns."""
        with self._connect() as conn:
            topics = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT DISTINCT topic_name FROM content_mappings
                    WHERE topic_name IS NOT NULL AND topic_name != ''
                    ORDER BY topic_name
                    """
                ).fetchall()
            ]
            types = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT DISTINCT content_type FROM content_mappings
                    ORDER BY content_type
                    """
                ).fetchall()
            ]
        return {"topics": topics, "content_types": types}

    def delete_by_content_id(self, content_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM content_mappings WHERE content_id = ?",
                (content_id,),
            )
        return cur.rowcount > 0

    def update_human_review(
        self,
        content_id: str,
        *,
        human_tags: list[ProposedKPTag],
        review_status: ReviewStatus,
        reviewer_notes: str = "",
    ) -> StoredMapping | None:
        existing = self.get_by_content_id(content_id)
        if not existing:
            return None
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE content_mappings SET
                    human_tags_json = ?,
                    review_status = ?,
                    reviewer_notes = ?,
                    updated_at = ?
                WHERE content_id = ?
                """,
                (
                    json.dumps([t.model_dump(mode="json") for t in human_tags]),
                    review_status.value,
                    reviewer_notes,
                    now,
                    content_id,
                ),
            )
        return self.get_by_content_id(content_id)

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM content_mappings").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM content_mappings WHERE review_status = 'pending'"
            ).fetchone()[0]
            flagged = conn.execute(
                """
                SELECT COUNT(*) FROM content_mappings
                WHERE json_extract(ai_result_json, '$.needs_human_review') = 1
                """
            ).fetchone()[0]
            approved = conn.execute(
                "SELECT COUNT(*) FROM content_mappings WHERE review_status = 'approved'"
            ).fetchone()[0]
        return {
            "total": total,
            "pending_review": pending,
            "flagged_for_human": flagged,
            "approved": approved,
        }

    def _row_to_model(self, row: sqlite3.Row) -> StoredMapping:
        ai = MappingResult.model_validate(json.loads(row["ai_result_json"]))
        human_raw = json.loads(row["human_tags_json"] or "[]")
        human = [ProposedKPTag.model_validate(t) for t in human_raw]
        try:
            status = ReviewStatus(row["review_status"])
        except ValueError:
            status = ReviewStatus.PENDING
        return StoredMapping(
            id=row["id"],
            content_id=row["content_id"],
            file_path=row["file_path"],
            content_type=row["content_type"],
            title=row["title"],
            topic_name=row["topic_name"],
            course_title=row["course_title"],
            ai_result=ai,
            human_tags=human,
            review_status=status,
            reviewer_notes=row["reviewer_notes"] or "",
            updated_at=row["updated_at"],
        )
