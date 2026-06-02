from __future__ import annotations

import calendar
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_for_group(text: str | None) -> str:
    """Aggressive normalization for exact-match grouping.

    Strips markdown emphasis, HTML tags, answer-option markers, then case-folds
    and collapses whitespace. Two questions whose only difference is formatting
    (e.g. *zip()* vs zip(), 'A)' vs 'a)') collapse to the same key.
    """
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r"[*_`]+", "", s)              # strip markdown emphasis chars
    s = re.sub(r"<[^>]+>", " ", s)            # strip inline HTML tags
    s = re.sub(r"\b[a-d]\s*[\)\.]", " ", s)   # 'a)' / 'A.' answer markers
    s = re.sub(r"\(\s*[a-d]\s*\)", " ", s)    # '(a)' markers
    s = re.sub(r"\s+", " ", s).strip()        # collapse whitespace
    s = s.strip(".,;:!?\"' ")                  # strip outer punctuation
    return s


def compute_group_key(question: str | None, company: str | None) -> str:
    q = _normalize_for_group(question)
    c = _normalize_for_group(company)
    h = hashlib.sha256(f"{q}|{c}".encode("utf-8")).hexdigest()
    return h[:32]


# Reusable across modules (curriculum decisions, frequency, etc.)
DURATION_PRESETS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}


def months_ago_iso(n: int, *, anchor: date | None = None) -> str:
    """Return ISO date N calendar months before anchor (default today)."""
    anchor = anchor or date.today()
    y, m = anchor.year, anchor.month - n
    while m <= 0:
        m += 12
        y -= 1
    d = min(anchor.day, calendar.monthrange(y, m)[1])
    return date(y, m, d).isoformat()


def resolve_date_range(
    *,
    duration: str | None,
    date_from: str | None,
    date_to: str | None,
    anchor: date | None = None,
) -> tuple[str | None, str | None]:
    """Resolve duration preset (1m/3m/6m/12m) + explicit dates into (from, to) ISO strings.

    Precedence: explicit date_from/date_to override preset bounds.
    duration='all' or None with no explicit dates -> (None, None).
    """
    anchor = anchor or date.today()
    df, dt = date_from or None, date_to or None
    if duration and duration in DURATION_PRESETS:
        preset_from = months_ago_iso(DURATION_PRESETS[duration], anchor=anchor)
        preset_to = anchor.isoformat()
        df = df or preset_from
        dt = dt or preset_to
    return df, dt


def _fingerprint(row: dict[str, Any]) -> str:
    parts = [
        (row.get("question") or "").strip().lower(),
        (row.get("company_name") or "").strip().lower(),
        (row.get("role") or "").strip().lower(),
        (row.get("interview_date") or "").strip(),
    ]
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:32]


class InterviewStore:
    """SQLite store for interview questions from the assessments sheet."""

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
                CREATE TABLE IF NOT EXISTS interview_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    row_key TEXT NOT NULL UNIQUE,
                    question_uuid TEXT,
                    question TEXT NOT NULL,
                    question_type TEXT,
                    skills_assessed_remarks TEXT,
                    remarks TEXT,
                    company_name TEXT,
                    role TEXT,
                    tech_stack TEXT,
                    optional_skills TEXT,
                    interview_date TEXT,
                    product TEXT,
                    job_type TEXT,
                    job_id TEXT,
                    minimum_ctc_lpa TEXT,
                    maximum_ctc_lpa TEXT,
                    round_category TEXT,
                    interview_process TEXT,
                    raw_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_iq_company ON interview_questions(company_name);
                CREATE INDEX IF NOT EXISTS idx_iq_role ON interview_questions(role);
                CREATE INDEX IF NOT EXISTS idx_iq_type ON interview_questions(question_type);
                CREATE INDEX IF NOT EXISTS idx_iq_tech ON interview_questions(tech_stack);
                CREATE INDEX IF NOT EXISTS idx_iq_date ON interview_questions(interview_date);

                CREATE TABLE IF NOT EXISTS interview_sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    fetched_rows INTEGER DEFAULT 0,
                    inserted INTEGER DEFAULT 0,
                    updated INTEGER DEFAULT 0,
                    unchanged INTEGER DEFAULT 0,
                    error TEXT,
                    duration_ms INTEGER
                );

                CREATE TABLE IF NOT EXISTS interview_question_groups (
                    group_key TEXT PRIMARY KEY,
                    exact_question TEXT NOT NULL,
                    company_name TEXT,
                    canonical_question TEXT,
                    canonical_slug TEXT,
                    normalized INTEGER NOT NULL DEFAULT 0,
                    normalizer_version TEXT,
                    merged_into TEXT,
                    member_count INTEGER NOT NULL DEFAULT 1,
                    representative_row_key TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_iqg_company ON interview_question_groups(company_name);
                CREATE INDEX IF NOT EXISTS idx_iqg_normalized ON interview_question_groups(normalized);
                CREATE INDEX IF NOT EXISTS idx_iqg_merged ON interview_question_groups(merged_into);
                CREATE INDEX IF NOT EXISTS idx_iqg_slug ON interview_question_groups(canonical_slug);
                """
            )
            self._add_column_if_missing(conn, "interview_questions", "group_key", "TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_iq_group ON interview_questions(group_key)"
            )
        self._backfill_groups()

    def _backfill_groups(self) -> None:
        """Recompute group_key for every interview row (uses current normalizer rules).

        Idempotent. After a normalizer change, rerunning collapses formerly-distinct
        groups into one and drops orphan tag rows that no longer match any
        canonical representative.
        """
        with self._connect() as conn:
            # 1) Recompute group_key on EVERY row — normalizer rules may have changed.
            rows = conn.execute(
                "SELECT id, row_key, question, company_name FROM interview_questions"
            ).fetchall()
            for r in rows:
                gk = compute_group_key(r["question"], r["company_name"])
                conn.execute(
                    "UPDATE interview_questions SET group_key = ? WHERE id = ?",
                    (gk, r["id"]),
                )

            # 2) Build the set of "live" group_keys.
            live_keys = {
                row["group_key"]
                for row in conn.execute(
                    "SELECT DISTINCT group_key FROM interview_questions "
                    "WHERE group_key IS NOT NULL AND group_key != ''"
                ).fetchall()
            }

            # 3) Drop group rows that no longer have any members (stale after recompute).
            #    Preserves merged_into history by NOT touching groups whose key is in live_keys.
            existing_groups = {
                row["group_key"]
                for row in conn.execute(
                    "SELECT group_key FROM interview_question_groups"
                ).fetchall()
            }
            stale = existing_groups - live_keys
            for sk in stale:
                conn.execute(
                    "DELETE FROM interview_question_groups WHERE group_key = ?",
                    (sk,),
                )

            # 4) Aggregate live keys and reconcile group rows.
            agg = conn.execute(
                "SELECT group_key, COUNT(*) AS n, MIN(first_seen_at) AS first_seen, "
                "MAX(last_seen_at) AS last_seen FROM interview_questions "
                "WHERE group_key IS NOT NULL AND group_key != '' GROUP BY group_key"
            ).fetchall()
            now = _utc_now()
            for g in agg:
                rep = conn.execute(
                    "SELECT row_key, question, company_name FROM interview_questions "
                    "WHERE group_key = ? ORDER BY id ASC LIMIT 1",
                    (g["group_key"],),
                ).fetchone()
                if rep is None:
                    continue
                existing = conn.execute(
                    "SELECT representative_row_key FROM interview_question_groups WHERE group_key = ?",
                    (g["group_key"],),
                ).fetchone()
                if existing:
                    # Repoint representative if the original rep no longer belongs to this group
                    conn.execute(
                        "UPDATE interview_question_groups SET member_count = ?, "
                        "last_seen_at = ?, updated_at = ?, representative_row_key = ? "
                        "WHERE group_key = ?",
                        (g["n"], g["last_seen"], now, rep["row_key"], g["group_key"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO interview_question_groups ("
                        "group_key, exact_question, company_name, member_count, "
                        "representative_row_key, first_seen_at, last_seen_at, created_at, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            g["group_key"],
                            rep["question"],
                            rep["company_name"],
                            g["n"],
                            rep["row_key"],
                            g["first_seen"],
                            g["last_seen"],
                            now,
                            now,
                        ),
                    )

            # 5) Drop tags (theory AND coding) whose row_key is no longer the
            #    representative of any canonical (un-merged) group. Reviewer evals survive.
            canonical_reps = {
                row[0]
                for row in conn.execute(
                    "SELECT g.representative_row_key FROM interview_question_groups g "
                    "WHERE g.merged_into IS NULL OR g.merged_into = ''"
                ).fetchall()
            }
            existing_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for tag_table in ("theory_question_tags", "coding_question_tags"):
                if tag_table not in existing_tables:
                    continue  # not created yet on very first boot
                stale_tags = [
                    row[0]
                    for row in conn.execute(
                        f"SELECT row_key FROM {tag_table}"
                    ).fetchall()
                    if row[0] not in canonical_reps
                ]
                for rk in stale_tags:
                    conn.execute(
                        f"DELETE FROM {tag_table} WHERE row_key = ?",
                        (rk,),
                    )

    # ---------- group queries ----------

    def get_group(self, group_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM interview_question_groups WHERE group_key = ?",
                (group_key,),
            ).fetchone()
        return dict(row) if row else None

    def list_groups(
        self,
        *,
        company_name: str | None = None,
        normalized: int | None = None,
        min_members: int = 1,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        clauses = ["(merged_into IS NULL OR merged_into = '')"]
        params: list[object] = []
        if company_name:
            clauses.append("company_name = ?")
            params.append(company_name)
        if normalized is not None:
            clauses.append("normalized = ?")
            params.append(normalized)
        if min_members > 1:
            clauses.append("member_count >= ?")
            params.append(min_members)
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM interview_question_groups WHERE {' AND '.join(clauses)} "
                f"ORDER BY member_count DESC, last_seen_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def members_of_group(self, group_key: str, *, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT row_key, question_uuid, question, company_name, role, "
                "interview_date, first_seen_at FROM interview_questions "
                "WHERE group_key = ? ORDER BY id ASC LIMIT ?",
                (group_key, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_questions_grouped(
        self,
        *,
        q: str | None = None,
        company_name: str | None = None,
        role: str | None = None,
        question_type: str | None = None,
        tech_stack: str | None = None,
        product: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        clauses, params = self._where(
            q=q,
            company_name=company_name,
            role=role,
            question_type=question_type,
            tech_stack=tech_stack,
            product=product,
            date_from=date_from,
            date_to=date_to,
            prefix="iq.",
        )
        clauses.append(
            "iq.row_key IN ("
            " SELECT representative_row_key FROM interview_question_groups "
            " WHERE merged_into IS NULL OR merged_into = ''"
            ")"
        )
        where = f"WHERE {' AND '.join(clauses)}"
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT iq.*,
                       gc.member_count AS group_member_count,
                       gc.canonical_question AS group_canonical_question,
                       gc.canonical_slug AS group_canonical_slug,
                       gc.representative_row_key AS group_representative_row_key,
                       gc.normalized AS group_normalized,
                       COALESCE(ct.row_key, tt.row_key) AS theory_row_key,
                       COALESCE(ct.verdict, tt.verdict) AS theory_verdict,
                       COALESCE(ct.overall_confidence, tt.overall_confidence) AS theory_confidence,
                       COALESCE(ct.review_status, tt.review_status) AS theory_review_status,
                       COALESCE(ct.updated_at, tt.updated_at) AS theory_updated_at,
                       COALESCE(ct.question_type, tt.question_type) AS theory_question_type,
                       COALESCE(ct.synthesis_quality, tt.synthesis_quality) AS theory_synthesis_quality,
                       COALESCE(ct.match_strategy, tt.match_strategy) AS theory_match_strategy
                FROM interview_questions iq
                LEFT JOIN interview_question_groups g  ON g.group_key  = iq.group_key
                LEFT JOIN interview_question_groups gc
                       ON gc.group_key = COALESCE(NULLIF(g.merged_into, ''), g.group_key)
                LEFT JOIN theory_question_tags tt
                       ON tt.row_key = COALESCE(gc.representative_row_key, iq.row_key)
                LEFT JOIN coding_question_tags ct
                       ON ct.row_key = COALESCE(gc.representative_row_key, iq.row_key)
                {where}
                ORDER BY COALESCE(iq.interview_date, '') DESC, iq.id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = self._row_to_dict_with_extras(r)
            for extra in ("group_member_count", "group_canonical_question", "group_canonical_slug", "group_normalized"):
                if extra in r.keys():
                    d[extra.replace("group_", "") if extra.startswith("group_canonical_") else extra] = r[extra]
            # Aliases to match the flat path naming used by frontend
            d["member_count"] = d.get("group_member_count")
            d["canonical_question"] = d.get("group_canonical_question") or d.get("canonical_question")
            d["canonical_slug"] = d.get("group_canonical_slug") or d.get("canonical_slug")
            out.append(d)
        return out

    def representative_row_keys(
        self, *, question_type: str | None = None
    ) -> list[str]:
        clauses = ["(g.merged_into IS NULL OR g.merged_into = '')"]
        params: list[object] = []
        sql = (
            "SELECT g.representative_row_key FROM interview_question_groups g "
            "JOIN interview_questions iq ON iq.row_key = g.representative_row_key "
        )
        if question_type:
            clauses.append("iq.question_type = ?")
            params.append(question_type)
        sql += "WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [r[0] for r in rows]

    def normalize_status(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN normalized = 0 AND (merged_into IS NULL OR merged_into = '') THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN normalized = 1 AND (merged_into IS NULL OR merged_into = '') THEN 1 ELSE 0 END) AS normalized,
                    SUM(CASE WHEN merged_into IS NOT NULL AND merged_into != '' THEN 1 ELSE 0 END) AS merged,
                    COUNT(*) AS total
                FROM interview_question_groups
                """
            ).fetchone()
        return {
            "pending": int(row["pending"] or 0),
            "normalized": int(row["normalized"] or 0),
            "merged": int(row["merged"] or 0),
            "total": int(row["total"] or 0),
        }

    def pending_normalization_groups(self, *, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interview_question_groups "
                "WHERE normalized = 0 AND (merged_into IS NULL OR merged_into = '') "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def normalized_groups_for_company(self, company_name: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interview_question_groups WHERE company_name = ? "
                "AND normalized = 1 AND (merged_into IS NULL OR merged_into = '')",
                (company_name,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_group_normalized(
        self,
        group_key: str,
        *,
        canonical_question: str,
        canonical_slug: str,
        normalizer_version: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE interview_question_groups SET canonical_question = ?, "
                "canonical_slug = ?, normalized = 1, normalizer_version = ?, updated_at = ? "
                "WHERE group_key = ?",
                (canonical_question, canonical_slug, normalizer_version, _utc_now(), group_key),
            )

    def merge_group(
        self, *, loser_key: str, winner_key: str, normalizer_version: str
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            loser = conn.execute(
                "SELECT * FROM interview_question_groups WHERE group_key = ?", (loser_key,)
            ).fetchone()
            winner = conn.execute(
                "SELECT * FROM interview_question_groups WHERE group_key = ?", (winner_key,)
            ).fetchone()
            if not loser or not winner:
                return
            conn.execute(
                "UPDATE interview_question_groups SET merged_into = ?, normalized = 1, "
                "normalizer_version = ?, canonical_question = ?, canonical_slug = ?, "
                "updated_at = ? WHERE group_key = ?",
                (
                    winner_key,
                    normalizer_version,
                    winner["canonical_question"],
                    winner["canonical_slug"],
                    now,
                    loser_key,
                ),
            )
            new_count = (winner["member_count"] or 0) + (loser["member_count"] or 0)
            new_last_seen = max(winner["last_seen_at"] or "", loser["last_seen_at"] or "")
            conn.execute(
                "UPDATE interview_question_groups SET member_count = ?, last_seen_at = ?, "
                "updated_at = ? WHERE group_key = ?",
                (new_count, new_last_seen, now, winner_key),
            )

    def upsert_many(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        stats = {"inserted": 0, "updated": 0, "unchanged": 0}
        now = _utc_now()
        columns = (
            "question_uuid",
            "question",
            "question_type",
            "skills_assessed_remarks",
            "remarks",
            "company_name",
            "role",
            "tech_stack",
            "optional_skills",
            "interview_date",
            "product",
            "job_type",
            "job_id",
            "minimum_ctc_lpa",
            "maximum_ctc_lpa",
            "round_category",
            "interview_process",
        )
        with self._connect() as conn:
            for row in rows:
                row_key = (row.get("question_uuid") or "").strip() or _fingerprint(row)
                raw = json.dumps(row, ensure_ascii=False)
                group_key = compute_group_key(row.get("question"), row.get("company_name"))
                existing = conn.execute(
                    "SELECT raw_json FROM interview_questions WHERE row_key = ?",
                    (row_key,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        f"""
                        INSERT INTO interview_questions (
                            row_key, {', '.join(columns)}, raw_json,
                            first_seen_at, last_seen_at, updated_at, group_key
                        ) VALUES (?, {', '.join(['?'] * len(columns))}, ?, ?, ?, ?, ?)
                        """,
                        (
                            row_key,
                            *[row.get(c) for c in columns],
                            raw,
                            now,
                            now,
                            now,
                            group_key,
                        ),
                    )
                    stats["inserted"] += 1
                    grp = conn.execute(
                        "SELECT member_count FROM interview_question_groups WHERE group_key = ?",
                        (group_key,),
                    ).fetchone()
                    if grp is None:
                        conn.execute(
                            "INSERT INTO interview_question_groups ("
                            "group_key, exact_question, company_name, member_count, "
                            "representative_row_key, first_seen_at, last_seen_at, "
                            "created_at, updated_at"
                            ") VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)",
                            (
                                group_key,
                                row.get("question") or "",
                                row.get("company_name"),
                                row_key,
                                now,
                                now,
                                now,
                                now,
                            ),
                        )
                    else:
                        conn.execute(
                            "UPDATE interview_question_groups SET "
                            "member_count = member_count + 1, last_seen_at = ?, updated_at = ? "
                            "WHERE group_key = ?",
                            (now, now, group_key),
                        )
                else:
                    if existing["raw_json"] == raw:
                        conn.execute(
                            "UPDATE interview_questions SET last_seen_at = ? WHERE row_key = ?",
                            (now, row_key),
                        )
                        stats["unchanged"] += 1
                    else:
                        set_clause = ", ".join(f"{c} = ?" for c in columns)
                        conn.execute(
                            f"""
                            UPDATE interview_questions SET
                                {set_clause},
                                raw_json = ?,
                                last_seen_at = ?,
                                updated_at = ?
                            WHERE row_key = ?
                            """,
                            (
                                *[row.get(c) for c in columns],
                                raw,
                                now,
                                now,
                                row_key,
                            ),
                        )
                        stats["updated"] += 1
        return stats

    def list_questions(
        self,
        *,
        q: str | None = None,
        company_name: str | None = None,
        role: str | None = None,
        question_type: str | None = None,
        tech_stack: str | None = None,
        product: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        clauses, params = self._where(
            q=q,
            company_name=company_name,
            role=role,
            question_type=question_type,
            tech_stack=tech_stack,
            product=product,
            date_from=date_from,
            date_to=date_to,
            prefix="iq.",
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT iq.*,
                       gc.member_count AS group_member_count,
                       gc.canonical_question AS group_canonical_question,
                       gc.canonical_slug AS group_canonical_slug,
                       gc.representative_row_key AS group_representative_row_key,
                       COALESCE(ct.row_key, tt.row_key) AS theory_row_key,
                       COALESCE(ct.verdict, tt.verdict) AS theory_verdict,
                       COALESCE(ct.overall_confidence, tt.overall_confidence) AS theory_confidence,
                       COALESCE(ct.review_status, tt.review_status) AS theory_review_status,
                       COALESCE(ct.updated_at, tt.updated_at) AS theory_updated_at,
                       COALESCE(ct.question_type, tt.question_type) AS theory_question_type,
                       COALESCE(ct.synthesis_quality, tt.synthesis_quality) AS theory_synthesis_quality,
                       COALESCE(ct.match_strategy, tt.match_strategy) AS theory_match_strategy
                FROM interview_questions iq
                LEFT JOIN interview_question_groups g  ON g.group_key  = iq.group_key
                LEFT JOIN interview_question_groups gc
                       ON gc.group_key = COALESCE(NULLIF(g.merged_into, ''), g.group_key)
                LEFT JOIN theory_question_tags tt
                       ON tt.row_key = COALESCE(gc.representative_row_key, iq.row_key)
                LEFT JOIN coding_question_tags ct
                       ON ct.row_key = COALESCE(gc.representative_row_key, iq.row_key)
                {where}
                ORDER BY COALESCE(iq.interview_date, '') DESC, iq.id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [self._row_to_dict_with_extras(r) for r in rows]

    def count(
        self,
        *,
        q: str | None = None,
        company_name: str | None = None,
        role: str | None = None,
        question_type: str | None = None,
        tech_stack: str | None = None,
        product: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        clauses, params = self._where(
            q=q,
            company_name=company_name,
            role=role,
            question_type=question_type,
            tech_stack=tech_stack,
            product=product,
            date_from=date_from,
            date_to=date_to,
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM interview_questions {where}", params
            ).fetchone()[0]

    def _where(
        self,
        *,
        q: str | None,
        company_name: str | None,
        role: str | None,
        question_type: str | None,
        tech_stack: str | None,
        product: str | None,
        date_from: str | None,
        date_to: str | None,
        prefix: str = "",
    ) -> tuple[list[str], list[object]]:
        """Build WHERE clauses. Pass prefix='iq.' when used in JOIN queries."""
        p = f"{prefix}" if prefix else ""
        clauses: list[str] = []
        params: list[object] = []
        if q:
            pattern = f"%{q}%"
            clauses.append(
                f"({p}question LIKE ? OR {p}company_name LIKE ? OR {p}role LIKE ?"
                f" OR {p}tech_stack LIKE ? OR {p}skills_assessed_remarks LIKE ?)"
            )
            params.extend([pattern] * 5)
        if company_name:
            clauses.append(f"{p}company_name = ?")
            params.append(company_name)
        if role:
            clauses.append(f"{p}role = ?")
            params.append(role)
        if question_type:
            clauses.append(f"{p}question_type = ?")
            params.append(question_type)
        if tech_stack:
            clauses.append(f"{p}tech_stack = ?")
            params.append(tech_stack)
        if product:
            clauses.append(f"{p}product = ?")
            params.append(product)
        if date_from:
            clauses.append(f"{p}interview_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append(f"{p}interview_date <= ?")
            params.append(date_to)
        return clauses, params

    def facets(self) -> dict[str, list[str]]:
        with self._connect() as conn:
            def distinct(col: str) -> list[str]:
                return [
                    r[0]
                    for r in conn.execute(
                        f"SELECT DISTINCT {col} FROM interview_questions "
                        f"WHERE {col} IS NOT NULL AND {col} != '' "
                        f"ORDER BY {col}"
                    ).fetchall()
                ]

            return {
                "companies": distinct("company_name"),
                "roles": distinct("role"),
                "question_types": distinct("question_type"),
                "tech_stacks": distinct("tech_stack"),
                "products": distinct("product"),
            }

    def begin_sync(self, *, trigger: str) -> int:
        now = _utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO interview_sync_log (started_at, status, trigger)
                VALUES (?, 'running', ?)
                """,
                (now, trigger),
            )
            return cur.lastrowid or 0

    def end_sync(
        self,
        sync_id: int,
        *,
        status: str,
        fetched_rows: int = 0,
        inserted: int = 0,
        updated: int = 0,
        unchanged: int = 0,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE interview_sync_log SET
                    finished_at = ?,
                    status = ?,
                    fetched_rows = ?,
                    inserted = ?,
                    updated = ?,
                    unchanged = ?,
                    error = ?,
                    duration_ms = ?
                WHERE id = ?
                """,
                (
                    _utc_now(),
                    status,
                    fetched_rows,
                    inserted,
                    updated,
                    unchanged,
                    error,
                    duration_ms,
                    sync_id,
                ),
            )

    def last_sync(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM interview_sync_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def recent_syncs(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM interview_sync_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d.pop("raw_json", None)
        return d

    def _row_to_dict_with_extras(self, row: sqlite3.Row) -> dict:
        """Helper for joined queries — keeps theory + group columns as a nested 'theory' obj."""
        d = dict(row)
        d.pop("raw_json", None)
        theory = {
            "row_key": d.pop("theory_row_key", None),
            "verdict": d.pop("theory_verdict", None),
            "overall_confidence": d.pop("theory_confidence", None),
            "review_status": d.pop("theory_review_status", None),
            "updated_at": d.pop("theory_updated_at", None),
            "question_type": d.pop("theory_question_type", None),
            "synthesis_quality": d.pop("theory_synthesis_quality", None),
            "match_strategy": d.pop("theory_match_strategy", None),
        }
        # If no tag exists, theory.row_key will be None.
        d["theory"] = theory if theory.get("row_key") else None
        d["group_representative_row_key"] = d.pop("group_representative_row_key", None)
        return d
