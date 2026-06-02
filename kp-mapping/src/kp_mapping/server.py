from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .env import load_env
from .interview_store import InterviewStore, resolve_date_range
from .interview_sync import run_sync
from .kp_catalog import load_catalog
from .theory.api import build_theory_router
from .theory.compile import cold_start_if_needed
from .theory.pipeline import tag_question
from .theory.retrieval import build_citations_fn
from .theory.store import TheoryStore

load_env()
from .models import ProposedKPTag, ReviewStatus
from .store import MappingStore

logger = logging.getLogger("kp_mapping.server")

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
DEFAULT_KP_JSON = REPO_ROOT / "curriculum" / "KPs-ProgrammingFoundations.json"
DEFAULT_DB = ROOT / "data" / "kp_mappings.db"
STATIC_DIR = ROOT / "static"
CURRICULUM_DIR = REPO_ROOT / "curriculum"
INTERVIEW_CONFIG = REPO_ROOT / "config" / "interview_sheet.json"
INTERVIEW_JSON_SNAPSHOT = REPO_ROOT / "interview-ingestion" / "data" / "interview_questions.json"

# Pilot mapping: course_title -> directory under /curriculum/
COURSE_DIRS: dict[str, str] = {
    "Programming Foundations": "ProgrammingFoundations",
}

DAILY_SYNC_HOUR = int(os.environ.get("INTERVIEW_SYNC_HOUR_UTC", "2"))
DAILY_SYNC_MINUTE = int(os.environ.get("INTERVIEW_SYNC_MINUTE_UTC", "0"))

SEED_PATH = REPO_ROOT / "evals" / "theory" / "seed.jsonl"


def _scheduled_sync() -> None:
    try:
        result = run_sync(
            config_path=INTERVIEW_CONFIG,
            store=interview_store,
            trigger="scheduled",
            json_snapshot_path=INTERVIEW_JSON_SNAPSHOT,
        )
        logger.info("Scheduled interview sync ok: %s", result)
        pending_rows_to_tag = _collect_rows_needing_tagging(result)
        if pending_rows_to_tag:
            logger.info(
                "Auto-tagging %d changed interview rows after scheduled sync",
                len(pending_rows_to_tag),
            )
            _auto_tag_pending_rows(pending_rows_to_tag)
    except Exception as exc:
        logger.exception("Scheduled interview sync failed: %s", exc)


def _cold_start_theory() -> None:
    try:
        result = cold_start_if_needed(
            seed_path=SEED_PATH,
            store=theory_store,
            catalog=get_catalog(),
            citations_for=citations_for,
        )
        logger.info("Theory cold-start: %s", result)
    except Exception as exc:
        logger.exception("Theory cold-start failed: %s", exc)


def _boot_normalize() -> None:
    """One-shot semantic merge after the backfill normalizer rules change."""
    try:
        from .normalize import normalize_pending_groups
        result = normalize_pending_groups(
            interview_store, limit=200, theory_store=theory_store, coding_store=coding_store
        )
        logger.info("Boot normalize: %s", result)
    except Exception as exc:
        logger.exception("Boot normalize failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _scheduled_sync,
        CronTrigger(hour=DAILY_SYNC_HOUR, minute=DAILY_SYNC_MINUTE),
        id="interview_daily_sync",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        "Scheduler started — daily interview sync at %02d:%02d UTC",
        DAILY_SYNC_HOUR,
        DAILY_SYNC_MINUTE,
    )
    # Run cold-start theory bootstrap in a worker thread so app startup is not blocked
    scheduler.add_job(_cold_start_theory, id="theory_cold_start", replace_existing=True)
    # One-shot semantic normalize for any pending groups (runs after backfill).
    scheduler.add_job(_boot_normalize, id="boot_normalize", replace_existing=True)
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="KP Mapping Review", version="0.1.0", lifespan=lifespan)

store = MappingStore(Path(os.environ.get("KP_MAPPING_DB", str(DEFAULT_DB))))
interview_store = InterviewStore(
    Path(os.environ.get("KP_MAPPING_DB", str(DEFAULT_DB)))
)
theory_store = TheoryStore(
    Path(os.environ.get("KP_MAPPING_DB", str(DEFAULT_DB)))
)
# CODING tags live in their own physical tables, same DB file. Shares the eval /
# feedback / prompt-version tables (those names are hard-coded inside TheoryStore).
coding_store = TheoryStore(
    Path(os.environ.get("KP_MAPPING_DB", str(DEFAULT_DB))),
    tags_table="coding_question_tags",
    history_table="coding_tag_history",
)
citations_for = build_citations_fn(store)  # default: reading_material
citations_for_coding = build_citations_fn(store, content_type="coding_question")


def citations_for_question_type(qt: str):
    if (qt or "").upper() == "CODING":
        return citations_for_coding
    return citations_for


def store_for(qt: str) -> TheoryStore:
    """Pick the tag store for a question_type."""
    return coding_store if (qt or "").upper() == "CODING" else theory_store


catalog = None


def get_catalog():
    global catalog
    if catalog is None:
        path = Path(os.environ.get("KP_CATALOG_JSON", str(DEFAULT_KP_JSON)))
        catalog = load_catalog(path)
    return catalog


class HumanReviewPayload(BaseModel):
    human_tags: list[ProposedKPTag]
    review_status: ReviewStatus
    reviewer_notes: str = ""


@app.get("/api/health")
def health():
    return {"ok": True, "stats": store.stats()}


def _slugify_course(title: str) -> str:
    return (
        title.strip()
        .lower()
        .replace("&", "and")
        .replace("/", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _count_content_files(course_title: str) -> int:
    dir_name = COURSE_DIRS.get(course_title)
    if not dir_name:
        return 0
    course_dir = CURRICULUM_DIR / dir_name
    if not course_dir.is_dir():
        return 0
    n = 0
    for p in course_dir.rglob("*.json"):
        name = p.name
        if (
            name.endswith("_reading_material.json")
            or name.endswith("_coding.json")
            or name.endswith("_project.json")
        ):
            n += 1
    return n


@app.get("/api/courses")
def list_courses():
    cat = get_catalog()
    kp_count = len(cat.knowledge_points)
    db_summary = {row["course_title"]: row["mapped_count"] for row in store.course_summary()}

    course_titles: list[str] = list(COURSE_DIRS.keys())
    for title in db_summary.keys():
        if title not in course_titles:
            course_titles.append(title)

    courses = []
    for title in course_titles:
        courses.append(
            {
                "course_id": _slugify_course(title),
                "course_title": title,
                "kp_count": kp_count,
                "content_count": _count_content_files(title),
                "mapped_count": db_summary.get(title, 0),
            }
        )
    return {"courses": courses}


@app.get("/api/kps/with-counts")
def list_kps_with_counts(
    course_id: str | None = None,
    q: str | None = None,
    min_content_count: int | None = None,
    tag_role: str | None = None,
    limit: int = 500,
):
    cat = get_catalog()
    kps = cat.knowledge_points

    course_title: str | None = None
    if course_id:
        for title in COURSE_DIRS.keys():
            if _slugify_course(title) == course_id:
                course_title = title
                break

    counts = store.kp_mapped_counts(course_title=course_title)

    if q:
        ql = q.lower()
        kps = [
            kp
            for kp in kps
            if ql in (kp.label or "").lower()
            or ql in (kp.source_kp_id or "").lower()
            or ql in (kp.label_enum or "").lower()
            or ql in (kp.description or "").lower()
        ]

    rows = []
    for kp in kps:
        entry = counts.get(kp.source_kp_id, {"count": 0, "tag_role_breakdown": {}})
        mc = entry["count"]
        roles = entry["tag_role_breakdown"]
        if min_content_count is not None and mc < min_content_count:
            continue
        if tag_role and roles.get(tag_role, 0) == 0:
            continue
        rows.append(
            {
                **kp.model_dump(),
                "mapped_content_count": mc,
                "tag_role_breakdown": roles,
            }
        )

    rows.sort(key=lambda r: (-r["mapped_content_count"], r["source_kp_id"]))
    rows = rows[:limit]
    return {"count": len(rows), "knowledge_points": rows}


@app.get("/api/kps")
def list_kps(q: str | None = None, limit: int = 200):
    cat = get_catalog()
    kps = cat.knowledge_points
    if q:
        q_lower = q.lower()
        kps = [
            kp
            for kp in kps
            if q_lower in kp.label.lower()
            or q_lower in kp.source_kp_id.lower()
            or q_lower in kp.label_enum.lower()
        ]
    return {
        "count": len(kps[:limit]),
        "knowledge_points": [kp.model_dump() for kp in kps[:limit]],
    }


@app.get("/api/mappings/facets")
def mapping_facets():
    return store.filter_facets()


@app.get("/api/mappings")
def list_mappings(
    review_status: ReviewStatus | None = None,
    needs_human_review: bool | None = None,
    content_type: str | None = None,
    topic_name: str | None = None,
    kp_id: str | None = None,
    confidence: str | None = None,
    has_tags: bool | None = None,
    q: str | None = None,
    limit: int = 2000,
    offset: int = 0,
):
    items = store.list_mappings(
        review_status=review_status,
        needs_human_review=needs_human_review,
        content_type=content_type,
        topic_name=topic_name,
        kp_id=kp_id,
        confidence=confidence,
        has_tags=has_tags,
        q=q,
        limit=limit,
        offset=offset,
    )
    return {
        "stats": store.stats(),
        "total": len(items),
        "items": [m.model_dump(mode="json") for m in items],
    }


@app.get("/api/mappings/{content_id}")
def get_mapping(content_id: str):
    row = store.get_by_content_id(content_id)
    if not row:
        raise HTTPException(404, "Mapping not found")
    return row.model_dump(mode="json")


@app.get("/api/content/{content_id}/body")
def get_content_body(content_id: str):
    """Return raw markdown / HTML body for a content piece (reading material or coding)."""
    from .content_loader import load_content_file
    row = store.get_by_content_id(content_id)
    if not row:
        raise HTTPException(404, "Mapping not found")
    try:
        piece = load_content_file(Path(row.file_path))
    except Exception as exc:
        raise HTTPException(500, f"Failed to load content: {exc}") from exc
    return {
        "content_id": content_id,
        "title": piece.title,
        "topic_name": piece.topic_name,
        "course_title": piece.course_title,
        "content_type": piece.content_type,
        "body_text": piece.body_text,
        "solution_text": piece.solution_text,
    }


@app.put("/api/mappings/{content_id}")
def update_mapping(content_id: str, payload: HumanReviewPayload):
    updated = store.update_human_review(
        content_id,
        human_tags=payload.human_tags,
        review_status=payload.review_status,
        reviewer_notes=payload.reviewer_notes,
    )
    if not updated:
        raise HTTPException(404, "Mapping not found")
    return updated.model_dump(mode="json")


# THEORY namespace — owns the shared /api/theory/* singletons.
app.include_router(
    build_theory_router(
        theory_store=theory_store,
        interview_store=interview_store,
        catalog_provider=get_catalog,
        citations_for=citations_for,
        citations_for_question_type=citations_for_question_type,
        seed_path=SEED_PATH,
        route_segment="theory-questions",
        question_type="THEORY",
        register_shared=True,
    )
)
# CODING namespace — physically separate tables, skips the shared singletons.
app.include_router(
    build_theory_router(
        theory_store=coding_store,
        interview_store=interview_store,
        catalog_provider=get_catalog,
        citations_for=citations_for,
        citations_for_question_type=citations_for_question_type,
        seed_path=SEED_PATH,
        route_segment="coding-questions",
        question_type="CODING",
        register_shared=False,
    )
)


def _auto_tag_pending_rows(row_keys: list[str]) -> None:
    """Background task: tag changed interview rows (THEORY and CODING)."""
    if not row_keys:
        return
    try:
        cat = get_catalog()
    except Exception as exc:
        logger.exception("Cannot load catalog for auto-tag: %s", exc)
        return
    iq_by_key: dict[str, dict] = {}
    for r in interview_store.list_questions(limit=10000):
        if r.get("row_key") in row_keys:
            iq_by_key[r["row_key"]] = r
    for row_key in row_keys:
        iq = iq_by_key.get(row_key)
        if not iq:
            continue
        qt = (iq.get("question_type") or "").upper()
        if qt not in {"THEORY", "CODING"}:
            continue
        try:
            tag_question(
                row_key=row_key,
                question_text=iq.get("question") or "",
                store=store_for(qt),
                catalog=cat,
                citations_for=citations_for_question_type(qt),
                question_type=qt,
                force_human_review=True,
            )
        except Exception as exc:
            logger.exception("Auto-tag failed for %s: %s", row_key, exc)


@app.get("/api/interview-questions")
def list_interview_questions(
    q: str | None = None,
    company_name: str | None = None,
    role: str | None = None,
    question_type: str | None = None,
    tech_stack: str | None = None,
    product: str | None = None,
    duration: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: bool = False,
    limit: int = 500,
    offset: int = 0,
):
    resolved_from, resolved_to = resolve_date_range(
        duration=duration, date_from=date_from, date_to=date_to
    )
    common = dict(
        q=q,
        company_name=company_name,
        role=role,
        question_type=question_type,
        tech_stack=tech_stack,
        product=product,
        date_from=resolved_from,
        date_to=resolved_to,
    )
    if group_by:
        items = interview_store.list_questions_grouped(
            **common, limit=limit, offset=offset
        )
    else:
        items = interview_store.list_questions(**common, limit=limit, offset=offset)
    filtered_count = interview_store.count(**common)
    return {
        "total": interview_store.count(),
        "filtered_total": filtered_count,
        "returned": len(items),
        "items": items,
        "group_by": group_by,
        "applied_date_range": {
            "duration": duration,
            "date_from": resolved_from,
            "date_to": resolved_to,
        },
    }


@app.delete("/api/interview-questions/{row_key}")
def delete_interview_question(row_key: str):
    deleted = interview_store.delete_question(row_key)
    if deleted is None:
        raise HTTPException(404, "interview question not found")
    # Remove all related tagging/workflow records for deleted interview rows.
    for rk in deleted["deleted_row_keys"]:
        theory_store.delete_row_workflow_data(rk)
        coding_store.delete_row_workflow_data(rk)
    return {
        "deleted": True,
        "row_key": row_key,
        "deleted_row_keys": deleted["deleted_row_keys"],
        "deleted_count": len(deleted["deleted_row_keys"]),
        "group_key": deleted.get("group_key"),
    }


@app.get("/api/interview-question-groups")
def list_interview_question_groups(
    company_name: str | None = None,
    normalized: int | None = None,
    min_members: int = 1,
    limit: int = 500,
    offset: int = 0,
):
    items = interview_store.list_groups(
        company_name=company_name,
        normalized=normalized,
        min_members=min_members,
        limit=limit,
        offset=offset,
    )
    return {
        "total": len(items),
        "items": items,
        "status": interview_store.normalize_status(),
    }


@app.get("/api/interview-question-groups/{group_key}/members")
def get_group_members(group_key: str):
    grp = interview_store.get_group(group_key)
    if not grp:
        raise HTTPException(404, "group not found")
    members = interview_store.members_of_group(group_key)
    return {"group": grp, "members": members}


@app.get("/api/interview-questions/normalize-status")
def normalize_status():
    return interview_store.normalize_status()


@app.post("/api/interview-questions/normalize-now")
def normalize_now(background_tasks: BackgroundTasks, limit: int = 50):
    from .normalize import normalize_pending_groups

    def _run() -> None:
        try:
            result = normalize_pending_groups(
                interview_store, limit=limit, theory_store=theory_store, coding_store=coding_store
            )
            logger.info("Normalize run: %s", result)
        except Exception as exc:
            logger.exception("Normalize run failed: %s", exc)

    background_tasks.add_task(_run)
    return {
        "enqueued": True,
        "limit": limit,
        "status": interview_store.normalize_status(),
    }


@app.get("/api/interview-questions/facets")
def interview_question_facets():
    return interview_store.facets()


@app.get("/api/interview-questions/sync-status")
def interview_sync_status():
    return {
        "last": interview_store.last_sync(),
        "recent": interview_store.recent_syncs(limit=10),
        "schedule": {
            "hour_utc": DAILY_SYNC_HOUR,
            "minute_utc": DAILY_SYNC_MINUTE,
            "trigger": "daily",
        },
    }


@app.post("/api/interview-questions/sync")
def interview_sync_now(background_tasks: BackgroundTasks):
    try:
        result = run_sync(
            config_path=INTERVIEW_CONFIG,
            store=interview_store,
            trigger="manual",
            json_snapshot_path=INTERVIEW_JSON_SNAPSHOT,
        )
    except Exception as exc:
        raise HTTPException(500, f"Sync failed: {exc}") from exc

    # Enqueue auto-tagging for changed rows across THEORY + CODING.
    pending_rows_to_tag = _collect_rows_needing_tagging(result)
    if pending_rows_to_tag:
        background_tasks.add_task(_auto_tag_pending_rows, pending_rows_to_tag)
        result["auto_tag_enqueued"] = len(pending_rows_to_tag)
    return result


def _collect_rows_needing_tagging(sync_result: dict) -> list[str]:
    """Rows requiring re-tag after sync: newly inserted or updated rows only."""
    inserted = set(sync_result.get("inserted_row_keys") or [])
    updated = set(sync_result.get("updated_row_keys") or [])
    candidate = inserted | updated
    if not candidate:
        return []
    valid_types = {"THEORY", "CODING"}
    rows_by_key = {
        r.get("row_key"): r for r in interview_store.list_questions(limit=20000) if r.get("row_key")
    }
    out = [
        rk
        for rk in sorted(candidate)
        if rk in rows_by_key and (rows_by_key[rk].get("question_type") or "").upper() in valid_types
    ]
    return out


@app.get("/")
def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "UI not found")
    return FileResponse(index_path)


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
