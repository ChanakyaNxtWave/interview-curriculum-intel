from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TheoryStore:
    """SQLite store for theory question tagging + coverage + evals + DSPy versions."""

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
                CREATE TABLE IF NOT EXISTS theory_question_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    row_key TEXT NOT NULL UNIQUE,
                    question_text TEXT NOT NULL,
                    required_kps_json TEXT NOT NULL DEFAULT '[]',
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    candidate_citations_json TEXT NOT NULL DEFAULT '[]',
                    verdict TEXT NOT NULL DEFAULT 'uncertain',
                    can_student_answer INTEGER NOT NULL DEFAULT 0,
                    rationale TEXT,
                    overall_confidence REAL NOT NULL DEFAULT 0,
                    ai_model TEXT,
                    prompt_version TEXT,
                    review_reasons_json TEXT NOT NULL DEFAULT '[]',
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    human_required_kps_json TEXT,
                    human_citations_json TEXT,
                    human_verdict TEXT,
                    reviewer_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tqt_status ON theory_question_tags(review_status);
                CREATE INDEX IF NOT EXISTS idx_tqt_verdict ON theory_question_tags(verdict);

                CREATE TABLE IF NOT EXISTS theory_question_evals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    row_key TEXT NOT NULL,
                    question TEXT NOT NULL,
                    gold_required_kps_json TEXT NOT NULL,
                    gold_citations_json TEXT NOT NULL,
                    gold_verdict TEXT NOT NULL,
                    gold_rationale TEXT,
                    source TEXT NOT NULL,
                    is_frozen INTEGER NOT NULL DEFAULT 1,
                    is_holdout INTEGER NOT NULL DEFAULT 0,
                    added_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tqe_source ON theory_question_evals(source);
                CREATE INDEX IF NOT EXISTS idx_tqe_holdout ON theory_question_evals(is_holdout);

                CREATE TABLE IF NOT EXISTS theory_prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    compiled_json TEXT NOT NULL,
                    fewshot_count INTEGER DEFAULT 0,
                    gold_count_at_compile INTEGER DEFAULT 0,
                    devset_agreement REAL,
                    notes TEXT,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tpv_active ON theory_prompt_versions(is_active);

                CREATE TABLE IF NOT EXISTS theory_eval_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_version TEXT NOT NULL,
                    model TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    verdict_agree INTEGER NOT NULL,
                    false_covered INTEGER NOT NULL,
                    false_not_covered INTEGER NOT NULL,
                    kp_jaccard_avg REAL,
                    avg_confidence REAL,
                    agreement_rate REAL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS theory_review_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    row_key TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    feedback_text TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    ai_verdict_at_time TEXT,
                    human_verdict TEXT,
                    added_by TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trf_row ON theory_review_feedback(row_key);
                CREATE INDEX IF NOT EXISTS idx_trf_severity ON theory_review_feedback(severity);

                CREATE TABLE IF NOT EXISTS theory_tag_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    row_key TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    ai_model TEXT,
                    verdict TEXT NOT NULL,
                    overall_confidence REAL NOT NULL,
                    required_kps_json TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    candidate_citations_json TEXT NOT NULL,
                    rejected_candidates_json TEXT NOT NULL DEFAULT '[]',
                    rationale TEXT,
                    judge_reasoning TEXT,
                    kp_identifier_reasoning TEXT,
                    review_reasons_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tth_row ON theory_tag_history(row_key);
                CREATE INDEX IF NOT EXISTS idx_tth_version ON theory_tag_history(prompt_version);
                """
            )
            self._add_column_if_missing(
                conn, "theory_question_tags", "rejected_candidates_json", "TEXT NOT NULL DEFAULT '[]'"
            )
            self._add_column_if_missing(
                conn, "theory_question_tags", "kp_identifier_reasoning", "TEXT"
            )
            self._add_column_if_missing(
                conn, "theory_question_tags", "judge_reasoning", "TEXT"
            )
            self._add_column_if_missing(
                conn, "theory_question_evals", "feedback_weight", "INTEGER NOT NULL DEFAULT 1"
            )
            self._add_column_if_missing(
                conn, "theory_question_evals", "feedback_ids_json", "TEXT NOT NULL DEFAULT '[]'"
            )

    # ---------- tags ----------

    def upsert_tag(
        self,
        *,
        row_key: str,
        question_text: str,
        required_kps: list[dict],
        citations: list[dict],
        candidate_citations: list[dict],
        rejected_candidates: list[dict] | None = None,
        verdict: str,
        rationale: str,
        kp_identifier_reasoning: str = "",
        judge_reasoning: str = "",
        overall_confidence: float,
        ai_model: str,
        prompt_version: str,
        review_reasons: list[str],
        review_status: str,
        can_student_answer: bool,
    ) -> dict:
        now = _utc_now()
        rejected = rejected_candidates or []
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO theory_question_tags (
                    row_key, question_text, required_kps_json, citations_json,
                    candidate_citations_json, rejected_candidates_json,
                    verdict, can_student_answer, rationale,
                    kp_identifier_reasoning, judge_reasoning,
                    overall_confidence, ai_model, prompt_version,
                    review_reasons_json, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(row_key) DO UPDATE SET
                    question_text = excluded.question_text,
                    required_kps_json = excluded.required_kps_json,
                    citations_json = excluded.citations_json,
                    candidate_citations_json = excluded.candidate_citations_json,
                    rejected_candidates_json = excluded.rejected_candidates_json,
                    verdict = excluded.verdict,
                    can_student_answer = excluded.can_student_answer,
                    rationale = excluded.rationale,
                    kp_identifier_reasoning = excluded.kp_identifier_reasoning,
                    judge_reasoning = excluded.judge_reasoning,
                    overall_confidence = excluded.overall_confidence,
                    ai_model = excluded.ai_model,
                    prompt_version = excluded.prompt_version,
                    review_reasons_json = excluded.review_reasons_json,
                    review_status = excluded.review_status,
                    updated_at = excluded.updated_at
                """,
                (
                    row_key,
                    question_text,
                    json.dumps(required_kps),
                    json.dumps(citations),
                    json.dumps(candidate_citations),
                    json.dumps(rejected),
                    verdict,
                    1 if can_student_answer else 0,
                    rationale,
                    kp_identifier_reasoning,
                    judge_reasoning,
                    overall_confidence,
                    ai_model,
                    prompt_version,
                    json.dumps(review_reasons),
                    review_status,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO theory_tag_history (
                    row_key, prompt_version, ai_model, verdict, overall_confidence,
                    required_kps_json, citations_json, candidate_citations_json,
                    rejected_candidates_json, rationale, judge_reasoning,
                    kp_identifier_reasoning, review_reasons_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_key,
                    prompt_version,
                    ai_model,
                    verdict,
                    overall_confidence,
                    json.dumps(required_kps),
                    json.dumps(citations),
                    json.dumps(candidate_citations),
                    json.dumps(rejected),
                    rationale,
                    judge_reasoning,
                    kp_identifier_reasoning,
                    json.dumps(review_reasons),
                    now,
                ),
            )
        row = self.get_tag(row_key)
        assert row is not None
        return row

    # ---------- feedback ----------

    def insert_feedback(
        self,
        *,
        row_key: str,
        prompt_version: str,
        feedback_type: str,
        feedback_text: str,
        severity: str,
        ai_verdict_at_time: str | None,
        human_verdict: str | None,
        added_by: str = "",
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO theory_review_feedback (
                    row_key, prompt_version, feedback_type, feedback_text,
                    severity, ai_verdict_at_time, human_verdict, added_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_key, prompt_version, feedback_type, feedback_text, severity,
                 ai_verdict_at_time, human_verdict, added_by, now),
            )
            return cur.lastrowid or 0

    def list_feedback(self, row_key: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM theory_review_feedback WHERE row_key = ? ORDER BY id DESC",
                (row_key,),
            ).fetchall()
        return [dict(r) for r in rows]

    def latest_feedback_text(self, row_key: str, *, limit: int = 3) -> str:
        """Severity-tagged most-recent reviewer feedback, joined for inline use
        in the judge prompt. Empty string if no feedback exists for this row.
        """
        rows = self.list_feedback(row_key)[:limit]
        if not rows:
            return ""
        return "\n".join(
            f"[{(r.get('severity') or 'medium').upper()}] {r.get('feedback_type','general')}: "
            f"{r.get('feedback_text','').strip()}"
            for r in rows
        )

    def feedback_weight_for(self, row_key: str) -> tuple[int, list[int]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, severity FROM theory_review_feedback WHERE row_key = ?",
                (row_key,),
            ).fetchall()
        if not rows:
            return 1, []
        weight_map = {"low": 1, "medium": 2, "high": 3}
        ids = [r["id"] for r in rows]
        weight = max(weight_map.get(r["severity"], 1) for r in rows)
        return weight, ids

    # ---------- tag history ----------

    def list_tag_history(self, row_key: str, *, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM theory_tag_history WHERE row_key = ? ORDER BY id DESC LIMIT ?",
                (row_key, limit),
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            for key in (
                "required_kps_json",
                "citations_json",
                "candidate_citations_json",
                "rejected_candidates_json",
                "review_reasons_json",
            ):
                raw = d.pop(key, None)
                short = key.removesuffix("_json")
                try:
                    d[short] = json.loads(raw) if raw else []
                except (TypeError, ValueError):
                    d[short] = []
            out.append(d)
        return out

    # ---------- improvement summary ----------

    def improvement_summary(self) -> dict:
        with self._connect() as conn:
            runs = conn.execute(
                "SELECT prompt_version, agreement_rate, total, created_at, trigger "
                "FROM theory_eval_runs ORDER BY id ASC"
            ).fetchall()
            golds = conn.execute(
                "SELECT row_key, gold_verdict, MAX(created_at) AS created_at "
                "FROM theory_question_evals WHERE is_frozen = 1 GROUP BY row_key"
            ).fetchall()
            gold_by_row = {g["row_key"]: g["gold_verdict"] for g in golds}
            hist_rows = conn.execute(
                "SELECT row_key, prompt_version, verdict, created_at "
                "FROM theory_tag_history ORDER BY id ASC"
            ).fetchall()
        per_row: dict[str, list[dict]] = {}
        for r in hist_rows:
            per_row.setdefault(r["row_key"], []).append(dict(r))
        fixed = 0
        regressed = 0
        rows_with_history = 0
        for row_key, gold_v in gold_by_row.items():
            entries = per_row.get(row_key, [])
            if len(entries) < 2:
                continue
            rows_with_history += 1
            latest = entries[-1]["verdict"]
            prev = entries[-2]["verdict"]
            if prev != gold_v and latest == gold_v:
                fixed += 1
            elif prev == gold_v and latest != gold_v:
                regressed += 1
        return {
            "fixed": fixed,
            "regressed": regressed,
            "rows_with_history": rows_with_history,
            "total_golds": len(gold_by_row),
            "trend": [
                {
                    "prompt_version": r["prompt_version"],
                    "agreement_rate": r["agreement_rate"],
                    "total": r["total"],
                    "trigger": r["trigger"],
                    "created_at": r["created_at"],
                }
                for r in runs
            ],
        }

    def delete_tag(self, row_key: str) -> bool:
        """Remove a stale theory_question_tags row (e.g. after group merge)."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM theory_question_tags WHERE row_key = ?", (row_key,)
            )
            return cur.rowcount > 0

    def get_tag(self, row_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM theory_question_tags WHERE row_key = ?",
                (row_key,),
            ).fetchone()
        return self._tag_row_to_dict(row) if row else None

    def list_tags(
        self,
        *,
        verdict: str | None = None,
        review_status: str | None = None,
        q: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        company_name: str | None = None,
        role: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        # Join interview_questions for date + company + role filters
        clauses: list[str] = []
        params: list[object] = []
        if verdict:
            clauses.append("t.verdict = ?")
            params.append(verdict)
        if review_status:
            clauses.append("t.review_status = ?")
            params.append(review_status)
        if q:
            pat = f"%{q}%"
            clauses.append("(t.question_text LIKE ? OR t.rationale LIKE ?)")
            params.extend([pat, pat])
        if date_from:
            clauses.append("iq.interview_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("iq.interview_date <= ?")
            params.append(date_to)
        if company_name:
            clauses.append("iq.company_name = ?")
            params.append(company_name)
        if role:
            clauses.append("iq.role = ?")
            params.append(role)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.*,
                       iq.company_name AS iq_company,
                       iq.role AS iq_role,
                       iq.question_type AS iq_question_type,
                       iq.interview_date AS iq_interview_date,
                       iq.tech_stack AS iq_tech_stack
                FROM theory_question_tags t
                LEFT JOIN interview_questions iq ON iq.row_key = t.row_key
                {where}
                ORDER BY t.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._tag_row_to_dict(r, with_iq=True) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT review_status, COUNT(*) FROM theory_question_tags GROUP BY review_status"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def count_by_verdict(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT verdict, COUNT(*) FROM theory_question_tags GROUP BY verdict"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def update_human_review(
        self,
        row_key: str,
        *,
        human_required_kps: list[dict],
        human_citations: list[dict],
        human_verdict: str,
        review_status: str,
        reviewer_notes: str = "",
    ) -> dict | None:
        existing = self.get_tag(row_key)
        if not existing:
            return None
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE theory_question_tags SET
                    human_required_kps_json = ?,
                    human_citations_json = ?,
                    human_verdict = ?,
                    review_status = ?,
                    reviewer_notes = ?,
                    updated_at = ?
                WHERE row_key = ?
                """,
                (
                    json.dumps(human_required_kps),
                    json.dumps(human_citations),
                    human_verdict,
                    review_status,
                    reviewer_notes,
                    now,
                    row_key,
                ),
            )
        return self.get_tag(row_key)

    # ---------- evals ----------

    def insert_eval(
        self,
        *,
        row_key: str,
        question: str,
        gold_required_kps: list[dict],
        gold_citations: list[dict],
        gold_verdict: str,
        gold_rationale: str,
        source: str,
        is_holdout: bool = False,
        feedback_weight: int = 1,
        feedback_ids: list[int] | None = None,
        added_by: str = "",
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO theory_question_evals (
                    row_key, question, gold_required_kps_json, gold_citations_json,
                    gold_verdict, gold_rationale, source, is_frozen, is_holdout,
                    feedback_weight, feedback_ids_json,
                    added_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_key,
                    question,
                    json.dumps(gold_required_kps),
                    json.dumps(gold_citations),
                    gold_verdict,
                    gold_rationale,
                    source,
                    1 if is_holdout else 0,
                    feedback_weight,
                    json.dumps(feedback_ids or []),
                    added_by,
                    now,
                    now,
                ),
            )
            return cur.lastrowid or 0

    def list_evals(
        self,
        *,
        is_holdout: bool | None = None,
        source: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = ["is_frozen = 1"]
        params: list[object] = []
        if is_holdout is not None:
            clauses.append("is_holdout = ?")
            params.append(1 if is_holdout else 0)
        if source:
            clauses.append("source = ?")
            params.append(source)
        where = f"WHERE {' AND '.join(clauses)}"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM theory_question_evals {where} ORDER BY id ASC",
                params,
            ).fetchall()
        return [self._eval_row_to_dict(r) for r in rows]

    def count_evals_since(self, iso_dt: str | None) -> int:
        with self._connect() as conn:
            if iso_dt:
                row = conn.execute(
                    "SELECT COUNT(*) FROM theory_question_evals WHERE is_frozen=1 AND created_at > ?",
                    (iso_dt,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM theory_question_evals WHERE is_frozen=1"
                ).fetchone()
        return row[0] if row else 0

    def eval_exists_for_row(self, row_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM theory_question_evals WHERE row_key = ? LIMIT 1",
                (row_key,),
            ).fetchone()
        return row is not None

    # ---------- prompt versions ----------

    def insert_prompt_version(
        self,
        *,
        version: str,
        compiled_json: str,
        fewshot_count: int,
        gold_count_at_compile: int,
        devset_agreement: float | None,
        notes: str = "",
        activate: bool = True,
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO theory_prompt_versions (
                    version, compiled_json, fewshot_count, gold_count_at_compile,
                    devset_agreement, notes, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version,
                    compiled_json,
                    fewshot_count,
                    gold_count_at_compile,
                    devset_agreement,
                    notes,
                    1 if activate else 0,
                    now,
                ),
            )
            new_id = cur.lastrowid or 0
            if activate:
                conn.execute(
                    "UPDATE theory_prompt_versions SET is_active = 0 WHERE id != ?",
                    (new_id,),
                )
            return new_id

    def get_active_prompt_version(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM theory_prompt_versions WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def list_prompt_versions(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, version, fewshot_count, gold_count_at_compile, "
                "devset_agreement, notes, is_active, created_at "
                "FROM theory_prompt_versions ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def activate_version(self, version_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM theory_prompt_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE theory_prompt_versions SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END",
                (version_id,),
            )
        return True

    def last_compile_at(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM theory_prompt_versions ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    # ---------- eval runs ----------

    def insert_eval_run(
        self,
        *,
        prompt_version: str,
        model: str,
        trigger: str,
        total: int,
        verdict_agree: int,
        false_covered: int,
        false_not_covered: int,
        kp_jaccard_avg: float,
        avg_confidence: float,
        agreement_rate: float,
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO theory_eval_runs (
                    prompt_version, model, trigger, total,
                    verdict_agree, false_covered, false_not_covered,
                    kp_jaccard_avg, avg_confidence, agreement_rate, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prompt_version,
                    model,
                    trigger,
                    total,
                    verdict_agree,
                    false_covered,
                    false_not_covered,
                    kp_jaccard_avg,
                    avg_confidence,
                    agreement_rate,
                    now,
                ),
            )
            return cur.lastrowid or 0

    def list_eval_runs(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM theory_eval_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- row -> dict helpers ----------

    def _tag_row_to_dict(self, row: sqlite3.Row, *, with_iq: bool = False) -> dict:
        d = dict(row)
        for key in (
            "required_kps_json",
            "citations_json",
            "candidate_citations_json",
            "human_required_kps_json",
            "human_citations_json",
            "review_reasons_json",
        ):
            raw = d.get(key)
            if raw:
                try:
                    d[key.removesuffix("_json")] = json.loads(raw)
                except (TypeError, ValueError):
                    d[key.removesuffix("_json")] = []
            else:
                d[key.removesuffix("_json")] = [] if key != "human_verdict" else None
            d.pop(key, None)
        d["can_student_answer"] = bool(d.get("can_student_answer", 0))
        if with_iq:
            d["interview"] = {
                "company_name": d.pop("iq_company", None),
                "role": d.pop("iq_role", None),
                "question_type": d.pop("iq_question_type", None),
                "interview_date": d.pop("iq_interview_date", None),
                "tech_stack": d.pop("iq_tech_stack", None),
            }
        return d

    def _eval_row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        for key in ("gold_required_kps_json", "gold_citations_json"):
            raw = d.pop(key, None)
            short = key.removesuffix("_json")
            try:
                d[short] = json.loads(raw) if raw else []
            except (TypeError, ValueError):
                d[short] = []
        d["is_frozen"] = bool(d.get("is_frozen", 0))
        d["is_holdout"] = bool(d.get("is_holdout", 0))
        return d
