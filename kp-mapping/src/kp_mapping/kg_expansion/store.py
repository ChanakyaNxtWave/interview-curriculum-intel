from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KgExpansionStore:
    """Persist IPA/LTA gap-expansion runs and proposed KPs/nodes."""

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
                CREATE TABLE IF NOT EXISTS kg_expansion_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    question_limit INTEGER,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    total_questions INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    stats_json TEXT NOT NULL DEFAULT '{}',
                    model_label TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_kg_exp_runs_course
                    ON kg_expansion_runs(course_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS kg_expansion_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    row_key TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    ipa_json TEXT NOT NULL DEFAULT '{}',
                    lta_json TEXT NOT NULL DEFAULT '{}',
                    normalized_json TEXT NOT NULL DEFAULT '{}',
                    mappings_json TEXT NOT NULL DEFAULT '[]',
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES kg_expansion_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_exp_q_run ON kg_expansion_questions(run_id);

                CREATE TABLE IF NOT EXISTS kg_expansion_proposed_kps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    proposed_kp_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    knowledge_node_id TEXT NOT NULL,
                    touch_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (run_id, proposed_kp_id),
                    FOREIGN KEY (run_id) REFERENCES kg_expansion_runs(id)
                );

                CREATE TABLE IF NOT EXISTS kg_expansion_proposed_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    knowledge_node_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    prerequisites_json TEXT NOT NULL DEFAULT '[]',
                    touch_count INTEGER NOT NULL DEFAULT 0,
                    proposed_kp_id TEXT,
                    UNIQUE (run_id, knowledge_node_id),
                    FOREIGN KEY (run_id) REFERENCES kg_expansion_runs(id)
                );

                CREATE TABLE IF NOT EXISTS kg_expansion_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    row_key TEXT NOT NULL,
                    proposed_kp_label TEXT,
                    feedback_type TEXT NOT NULL,
                    feedback_text TEXT,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    human_verdict TEXT NOT NULL,
                    added_by TEXT NOT NULL DEFAULT 'reviewer',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (run_id) REFERENCES kg_expansion_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_kgef_run ON kg_expansion_feedback(run_id);
                CREATE INDEX IF NOT EXISTS idx_kgef_verdict ON kg_expansion_feedback(human_verdict);
                CREATE INDEX IF NOT EXISTS idx_kgef_type ON kg_expansion_feedback(feedback_type);
                """
            )

    def create_run(
        self,
        *,
        course_id: str,
        question_limit: int | None = None,
        total_questions: int = 0,
    ) -> dict:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO kg_expansion_runs (
                    course_id, status, question_limit, total_questions,
                    created_at, updated_at
                ) VALUES (?, 'pending', ?, ?, ?, ?)
                """,
                (course_id, question_limit, total_questions, now, now),
            )
            run_id = int(cur.lastrowid)
        return self.get_run(run_id) or {}

    def update_run(
        self,
        run_id: int,
        *,
        status: str | None = None,
        processed_count: int | None = None,
        error_message: str | None = None,
        stats: dict | None = None,
        model_label: str | None = None,
        completed: bool = False,
    ) -> None:
        fields: list[str] = []
        params: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if processed_count is not None:
            fields.append("processed_count = ?")
            params.append(processed_count)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if stats is not None:
            fields.append("stats_json = ?")
            params.append(json.dumps(stats))
        if model_label is not None:
            fields.append("model_label = ?")
            params.append(model_label)
        fields.append("updated_at = ?")
        params.append(_utc_now())
        if completed:
            fields.append("completed_at = ?")
            params.append(_utc_now())
        params.append(run_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE kg_expansion_runs SET {', '.join(fields)} WHERE id = ?",
                params,
            )

    def get_run(self, run_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM kg_expansion_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if not row:
            return None
        return self._run_row(row)

    def list_runs(self, course_id: str, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM kg_expansion_runs
                WHERE course_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (course_id, limit),
            ).fetchall()
        return [self._run_row(r) for r in rows]

    def get_latest_completed_run(self, course_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM kg_expansion_runs
                WHERE course_id = ? AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                (course_id,),
            ).fetchone()
        return self._run_row(row) if row else None

    def save_question_result(
        self,
        *,
        run_id: int,
        row_key: str,
        question_type: str,
        question_text: str,
        ipa: dict,
        lta: dict,
        normalized: dict,
        mappings: list[dict],
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_expansion_questions (
                    run_id, row_key, question_type, question_text,
                    ipa_json, lta_json, normalized_json, mappings_json,
                    error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row_key,
                    question_type,
                    question_text,
                    json.dumps(ipa),
                    json.dumps(lta),
                    json.dumps(normalized),
                    json.dumps(mappings),
                    error_message,
                    _utc_now(),
                ),
            )

    def upsert_proposed_kp(
        self,
        *,
        run_id: int,
        proposed_kp_id: str,
        label: str,
        description: str,
        knowledge_node_id: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_expansion_proposed_kps (
                    run_id, proposed_kp_id, label, description, knowledge_node_id, touch_count
                ) VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(run_id, proposed_kp_id) DO UPDATE SET
                    label = excluded.label,
                    description = excluded.description
                """,
                (run_id, proposed_kp_id, label, description, knowledge_node_id),
            )

    def upsert_proposed_node(
        self,
        *,
        run_id: int,
        knowledge_node_id: str,
        label: str,
        description: str,
        prerequisites: list[str],
        proposed_kp_id: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_expansion_proposed_nodes (
                    run_id, knowledge_node_id, label, description,
                    prerequisites_json, touch_count, proposed_kp_id
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(run_id, knowledge_node_id) DO UPDATE SET
                    label = excluded.label,
                    description = excluded.description,
                    prerequisites_json = excluded.prerequisites_json,
                    proposed_kp_id = excluded.proposed_kp_id
                """,
                (
                    run_id,
                    knowledge_node_id,
                    label,
                    description,
                    json.dumps(prerequisites),
                    proposed_kp_id,
                ),
            )

    def recompute_touch_counts(self, run_id: int) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT mappings_json FROM kg_expansion_questions WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        kp_counts: dict[str, int] = {}
        node_counts: dict[str, int] = {}
        for row in rows:
            mappings = json.loads(row["mappings_json"] or "[]")
            seen_kp: set[str] = set()
            seen_node: set[str] = set()
            for m in mappings:
                if m.get("match_type") == "new":
                    pk = m.get("proposed_kp_id")
                    nid = m.get("knowledge_node_id")
                    if pk and pk not in seen_kp:
                        kp_counts[pk] = kp_counts.get(pk, 0) + 1
                        seen_kp.add(pk)
                    if nid and nid not in seen_node:
                        node_counts[nid] = node_counts.get(nid, 0) + 1
                        seen_node.add(nid)
                elif m.get("match_type") == "existing_proposed":
                    pk = m.get("proposed_kp_id")
                    nid = m.get("knowledge_node_id")
                    if pk and pk not in seen_kp:
                        kp_counts[pk] = kp_counts.get(pk, 0) + 1
                        seen_kp.add(pk)
                    if nid and nid not in seen_node:
                        node_counts[nid] = node_counts.get(nid, 0) + 1
                        seen_node.add(nid)

        with self._connect() as conn:
            conn.execute(
                "UPDATE kg_expansion_proposed_kps SET touch_count = 0 WHERE run_id = ?",
                (run_id,),
            )
            conn.execute(
                "UPDATE kg_expansion_proposed_nodes SET touch_count = 0 WHERE run_id = ?",
                (run_id,),
            )
            for pk, count in kp_counts.items():
                conn.execute(
                    """
                    UPDATE kg_expansion_proposed_kps SET touch_count = ?
                    WHERE run_id = ? AND proposed_kp_id = ?
                    """,
                    (count, run_id, pk),
                )
            for nid, count in node_counts.items():
                conn.execute(
                    """
                    UPDATE kg_expansion_proposed_nodes SET touch_count = ?
                    WHERE run_id = ? AND knowledge_node_id = ?
                    """,
                    (count, run_id, nid),
                )

    def list_questions(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM kg_expansion_questions
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            d["ipa"] = json.loads(d.pop("ipa_json") or "{}")
            d["lta"] = json.loads(d.pop("lta_json") or "{}")
            d["normalized"] = json.loads(d.pop("normalized_json") or "{}")
            d["mappings"] = json.loads(d.pop("mappings_json") or "[]")
            out.append(d)
        return out

    def list_proposed_kps(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM kg_expansion_proposed_kps
                WHERE run_id = ?
                ORDER BY touch_count DESC, label ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_proposed_nodes(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM kg_expansion_proposed_nodes
                WHERE run_id = ?
                ORDER BY touch_count DESC, label ASC
                """,
                (run_id,),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            d["prerequisites"] = json.loads(d.pop("prerequisites_json") or "[]")
            out.append(d)
        return out

    def purge_all_data(self) -> dict[str, int]:
        """Delete all gap-expansion runs and any legacy proposed KP/node rows."""
        with self._connect() as conn:
            n_nodes = conn.execute(
                "DELETE FROM kg_expansion_proposed_nodes"
            ).rowcount
            n_kps = conn.execute("DELETE FROM kg_expansion_proposed_kps").rowcount
            n_questions = conn.execute(
                "DELETE FROM kg_expansion_questions"
            ).rowcount
            n_runs = conn.execute("DELETE FROM kg_expansion_runs").rowcount
        return {
            "runs": n_runs,
            "questions": n_questions,
            "proposed_kps": n_kps,
            "proposed_nodes": n_nodes,
        }

    # ---------- expansion feedback ----------

    def save_expansion_feedback(
        self,
        *,
        run_id: int,
        row_key: str,
        proposed_kp_label: str | None,
        feedback_type: str,
        feedback_text: str | None,
        severity: str = "medium",
        human_verdict: str,
        added_by: str = "reviewer",
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO kg_expansion_feedback (
                    run_id, row_key, proposed_kp_label, feedback_type,
                    feedback_text, severity, human_verdict, added_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, row_key, proposed_kp_label, feedback_type,
                 feedback_text, severity, human_verdict, added_by, now),
            )
            return cur.lastrowid or 0

    def list_expansion_feedback(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM kg_expansion_feedback WHERE run_id = ? ORDER BY id DESC",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_rejection_patterns(self, *, limit: int = 20) -> str:
        """Recent rejected KP labels grouped by feedback_type — injected into KP proposal prompt."""
        from collections import defaultdict
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT feedback_type, proposed_kp_label, severity
                FROM kg_expansion_feedback
                WHERE human_verdict = 'rejected' AND proposed_kp_label IS NOT NULL
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit * 4,),
            ).fetchall()
        if not rows:
            return ""
        groups: dict[str, list[str]] = defaultdict(list)
        seen: set[str] = set()
        for r in rows:
            ft = r["feedback_type"] or "general"
            label = (r["proposed_kp_label"] or "").strip()
            if not label:
                continue
            key = f"{ft}:{label.lower()}"
            if key in seen:
                continue
            seen.add(key)
            if len(groups[ft]) < 5:
                groups[ft].append(label)
        if not groups:
            return ""
        lines: list[str] = []
        for ft, labels in sorted(groups.items()):
            lines.append(f"[{ft}]")
            for lb in labels:
                lines.append(f"  - {lb}")
        return "\n".join(lines)

    def count_new_feedback_since(self, iso_dt: str | None) -> int:
        """Count rejected feedback rows newer than iso_dt (or all if None)."""
        with self._connect() as conn:
            if iso_dt is None:
                row = conn.execute(
                    "SELECT COUNT(*) FROM kg_expansion_feedback WHERE human_verdict = 'rejected'"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM kg_expansion_feedback "
                    "WHERE human_verdict = 'rejected' AND created_at > ?",
                    (iso_dt,),
                ).fetchone()
        return row[0] if row else 0

    @staticmethod
    def _run_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["stats"] = json.loads(d.pop("stats_json") or "{}")
        return d
