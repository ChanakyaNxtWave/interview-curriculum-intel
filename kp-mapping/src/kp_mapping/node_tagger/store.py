from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NodeTaggerStore:
    """SQLite store for node_tagger runs, questions, proposed nodes, and canonical nodes."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _add_column_if_missing(
        self, conn: sqlite3.Connection, table: str, column: str, ddl: str
    ) -> None:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS node_tagger_runs (
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
                CREATE INDEX IF NOT EXISTS idx_nt_runs_course
                    ON node_tagger_runs(course_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS node_tagger_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    row_key TEXT NOT NULL,
                    question_type TEXT NOT NULL DEFAULT 'THEORY',
                    question_text TEXT NOT NULL,
                    coverage_status TEXT,
                    existing_node_ids_json TEXT NOT NULL DEFAULT '[]',
                    new_nodes_json TEXT NOT NULL DEFAULT '[]',
                    reasoning TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES node_tagger_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_nt_questions_run
                    ON node_tagger_questions(run_id);
                CREATE INDEX IF NOT EXISTS idx_nt_questions_row_key
                    ON node_tagger_questions(row_key);

                CREATE TABLE IF NOT EXISTS node_tagger_proposed_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    knowledge_node_id TEXT NOT NULL,
                    normalized_label TEXT NOT NULL,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL,
                    prerequisites_json TEXT NOT NULL DEFAULT '[]',
                    depth_level INTEGER NOT NULL DEFAULT 0,
                    question_row_keys_json TEXT NOT NULL DEFAULT '[]',
                    approval_status TEXT NOT NULL DEFAULT 'pending',
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, normalized_label),
                    FOREIGN KEY (run_id) REFERENCES node_tagger_runs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_nt_proposed_run
                    ON node_tagger_proposed_nodes(run_id);

                CREATE TABLE IF NOT EXISTS node_tagger_canonical_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    knowledge_node_id TEXT NOT NULL UNIQUE,
                    normalized_label TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL,
                    prerequisites_json TEXT NOT NULL DEFAULT '[]',
                    depth_level INTEGER NOT NULL DEFAULT 0,
                    source_run_id INTEGER,
                    approved_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Idempotent migrations for existing DBs that lack the new columns
            self._add_column_if_missing(
                conn, "node_tagger_proposed_nodes", "approval_status",
                "TEXT NOT NULL DEFAULT 'pending'"
            )
            self._add_column_if_missing(
                conn, "node_tagger_proposed_nodes", "approved_at", "TEXT"
            )

    # ------------------------------------------------------------------ runs

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
                INSERT INTO node_tagger_runs
                    (course_id, status, question_limit, total_questions, created_at, updated_at)
                VALUES (?, 'pending', ?, ?, ?, ?)
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
        now = _utc_now()
        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]
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
        if completed:
            fields.append("completed_at = ?")
            params.append(now)
        params.append(run_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE node_tagger_runs SET {', '.join(fields)} WHERE id = ?",
                params,
            )

    def get_run(self, run_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM node_tagger_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._run_row(row) if row else None

    def list_runs(self, course_id: str, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM node_tagger_runs WHERE course_id = ?"
                " ORDER BY created_at DESC LIMIT ?",
                (course_id, limit),
            ).fetchall()
        return [self._run_row(r) for r in rows]

    def get_latest_completed_run(self, course_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM node_tagger_runs"
                " WHERE course_id = ? AND status = 'completed'"
                " ORDER BY completed_at DESC LIMIT 1",
                (course_id,),
            ).fetchone()
        return self._run_row(row) if row else None

    def _run_row(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["stats"] = json.loads(d.pop("stats_json") or "{}")
        except (TypeError, ValueError):
            d["stats"] = {}
        return d

    # ------------------------------------------------------------ questions

    def save_question_result(
        self,
        *,
        run_id: int,
        row_key: str,
        question_type: str,
        question_text: str,
        coverage_status: str | None,
        existing_node_ids: list[str],
        new_nodes: list[dict],
        reasoning: str | None,
        error_message: str | None,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO node_tagger_questions
                    (run_id, row_key, question_type, question_text,
                     coverage_status, existing_node_ids_json, new_nodes_json,
                     reasoning, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row_key,
                    question_type,
                    question_text,
                    coverage_status,
                    json.dumps(existing_node_ids),
                    json.dumps(new_nodes),
                    reasoning,
                    error_message,
                    now,
                ),
            )

    def get_processed_row_keys(self) -> set[str]:
        """Return row_keys of all questions successfully processed in ANY run."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT row_key FROM node_tagger_questions"
                " WHERE coverage_status IS NOT NULL"
            ).fetchall()
        return {r["row_key"] for r in rows}

    def list_questions(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM node_tagger_questions WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            for key in ("existing_node_ids_json", "new_nodes_json"):
                raw = d.pop(key, None)
                short = key.removesuffix("_json")
                try:
                    d[short] = json.loads(raw) if raw else []
                except (TypeError, ValueError):
                    d[short] = []
            out.append(d)
        return out

    # ---------------------------------------------------- proposed nodes

    def upsert_proposed_node(
        self,
        *,
        run_id: int,
        knowledge_node_id: str,
        label: str,
        description: str,
        prerequisites: list[str],
        depth_level: int,
        row_key: str,
    ) -> None:
        """Insert or append row_key for an existing normalized label within a run."""
        normalized = label.strip().lower()
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, question_row_keys_json FROM node_tagger_proposed_nodes"
                " WHERE run_id = ? AND normalized_label = ?",
                (run_id, normalized),
            ).fetchone()
            if existing:
                try:
                    keys: list[str] = json.loads(existing["question_row_keys_json"] or "[]")
                except (TypeError, ValueError):
                    keys = []
                if row_key not in keys:
                    keys.append(row_key)
                conn.execute(
                    "UPDATE node_tagger_proposed_nodes"
                    " SET question_row_keys_json = ? WHERE id = ?",
                    (json.dumps(keys), existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO node_tagger_proposed_nodes
                        (run_id, knowledge_node_id, normalized_label, label,
                         description, prerequisites_json, depth_level,
                         question_row_keys_json, approval_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        run_id,
                        knowledge_node_id,
                        normalized,
                        label,
                        description,
                        json.dumps(prerequisites),
                        depth_level,
                        json.dumps([row_key]),
                        now,
                    ),
                )

    def set_node_approval(
        self,
        run_id: int,
        knowledge_node_id: str,
        status: str,
    ) -> dict | None:
        """Set approval_status on a proposed node. If approved, copy to canonical_nodes."""
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM node_tagger_proposed_nodes"
                " WHERE run_id = ? AND knowledge_node_id = ?",
                (run_id, knowledge_node_id),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE node_tagger_proposed_nodes"
                " SET approval_status = ?, approved_at = ? WHERE id = ?",
                (status, now if status == "approved" else None, row["id"]),
            )
            if status == "approved":
                try:
                    prereqs = json.loads(row["prerequisites_json"] or "[]")
                except (TypeError, ValueError):
                    prereqs = []
                conn.execute(
                    """
                    INSERT INTO node_tagger_canonical_nodes
                        (knowledge_node_id, normalized_label, label, description,
                         prerequisites_json, depth_level, source_run_id,
                         approved_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(normalized_label) DO UPDATE SET
                        knowledge_node_id = excluded.knowledge_node_id,
                        label = excluded.label,
                        description = excluded.description,
                        prerequisites_json = excluded.prerequisites_json,
                        depth_level = excluded.depth_level,
                        source_run_id = excluded.source_run_id,
                        approved_at = excluded.approved_at
                    """,
                    (
                        row["knowledge_node_id"],
                        row["normalized_label"],
                        row["label"],
                        row["description"],
                        json.dumps(prereqs),
                        row["depth_level"],
                        run_id,
                        now,
                        now,
                    ),
                )

        # Return the updated row
        with self._connect() as conn:
            updated = conn.execute(
                "SELECT * FROM node_tagger_proposed_nodes"
                " WHERE run_id = ? AND knowledge_node_id = ?",
                (run_id, knowledge_node_id),
            ).fetchone()
        return self._proposed_node_row(updated) if updated else None

    def list_proposed_nodes(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM node_tagger_proposed_nodes WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [self._proposed_node_row(r) for r in rows]

    def _proposed_node_row(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        for key in ("prerequisites_json", "question_row_keys_json"):
            raw = d.pop(key, None)
            short = key.removesuffix("_json")
            try:
                d[short] = json.loads(raw) if raw else []
            except (TypeError, ValueError):
                d[short] = []
        return d

    def enrich_proposed_nodes_with_companies(
        self, nodes: list[dict]
    ) -> list[dict]:
        """Attach touch_count (unique companies) and companies list to each node."""
        if not nodes:
            return nodes
        all_row_keys: set[str] = set()
        for n in nodes:
            all_row_keys.update(n.get("question_row_keys") or [])
        if not all_row_keys:
            for n in nodes:
                n["touch_count"] = 0
                n["companies"] = []
            return nodes

        placeholders = ",".join("?" * len(all_row_keys))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT row_key, company_name FROM interview_questions"
                f" WHERE row_key IN ({placeholders})",
                list(all_row_keys),
            ).fetchall()
        rk_to_company: dict[str, str] = {
            r["row_key"]: (r["company_name"] or "") for r in rows
        }
        for n in nodes:
            rks = n.get("question_row_keys") or []
            companies = sorted(
                {rk_to_company[rk] for rk in rks if rk in rk_to_company and rk_to_company[rk]}
            )
            n["touch_count"] = len(companies)
            n["companies"] = companies
        return nodes

    # ------------------------------------------------------- canonical nodes

    def list_canonical_nodes(self) -> list[dict]:
        """All approved canonical nodes across all runs."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM node_tagger_canonical_nodes ORDER BY approved_at DESC"
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            raw = d.pop("prerequisites_json", None)
            try:
                d["prerequisites"] = json.loads(raw) if raw else []
            except (TypeError, ValueError):
                d["prerequisites"] = []
            out.append(d)
        return out

    # ----------------------------------------------------------------- purge

    def purge_all_data(self) -> dict:
        with self._connect() as conn:
            canonical_del = conn.execute("DELETE FROM node_tagger_canonical_nodes").rowcount
            nodes_del = conn.execute("DELETE FROM node_tagger_proposed_nodes").rowcount
            qs_del = conn.execute("DELETE FROM node_tagger_questions").rowcount
            runs_del = conn.execute("DELETE FROM node_tagger_runs").rowcount
        return {
            "runs": runs_del,
            "questions": qs_del,
            "proposed_nodes": nodes_del,
            "canonical_nodes": canonical_del,
        }
