from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

# Ordered list of pipeline stages surfaced to the UI.
STAGES: list[str] = [
    "start",
    "load_active_prompt",
    "identify_kps",
    "kps_done",
    "retrieve_citations",
    "citations_done",
    "judge_coverage",
    "judge_done",
    "synthesize_answer",
    "synthesize_done",
    "gating",
    "persisting",
    "done",
]

_lock = threading.Lock()
_progress: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_MAX_TRACKED = 200


def _now_ms() -> int:
    return int(time.time() * 1000)


def start(row_key: str, *, prompt_version: str | None = None, trigger: str = "manual") -> None:
    with _lock:
        _progress[row_key] = {
            "row_key": row_key,
            "stage": "start",
            "trigger": trigger,
            "prompt_version": prompt_version,
            "started_at_ms": _now_ms(),
            "updated_at_ms": _now_ms(),
            "elapsed_ms": 0,
            "events": [{"stage": "start", "at_ms": _now_ms(), "note": "queued"}],
            "kps_count": 0,
            "candidates_count": 0,
            "accepted_count": 0,
            "verdict": None,
            "confidence": None,
            "error": None,
            "result": None,
            "completed": False,
        }
        while len(_progress) > _MAX_TRACKED:
            _progress.popitem(last=False)


def emit(row_key: str, stage: str, **fields: Any) -> None:
    with _lock:
        rec = _progress.get(row_key)
        if not rec:
            return
        rec["stage"] = stage
        rec["updated_at_ms"] = _now_ms()
        rec["elapsed_ms"] = rec["updated_at_ms"] - rec["started_at_ms"]
        for k, v in fields.items():
            rec[k] = v
        rec["events"].append({"stage": stage, "at_ms": rec["updated_at_ms"], **fields})


def finish(row_key: str, *, result: dict | None = None, error: str | None = None) -> None:
    with _lock:
        rec = _progress.get(row_key)
        if not rec:
            return
        rec["stage"] = "error" if error else "done"
        rec["updated_at_ms"] = _now_ms()
        rec["elapsed_ms"] = rec["updated_at_ms"] - rec["started_at_ms"]
        rec["completed"] = True
        rec["error"] = error
        if result is not None:
            rec["result"] = {
                "verdict": result.get("verdict"),
                "overall_confidence": result.get("overall_confidence"),
                "review_status": result.get("review_status"),
                "required_kps_count": len(result.get("required_kps") or []),
                "citations_count": len(result.get("citations") or []),
                "candidate_citations_count": len(result.get("candidate_citations") or []),
            }
        rec["events"].append({"stage": rec["stage"], "at_ms": rec["updated_at_ms"]})


def get(row_key: str) -> dict | None:
    with _lock:
        rec = _progress.get(row_key)
        return dict(rec) if rec else None


def clear(row_key: str) -> None:
    with _lock:
        _progress.pop(row_key, None)
