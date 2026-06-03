from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
FEWSHOT_PATH = REPO_ROOT / "evals" / "kg_expansion" / "fewshot_curriculum.json"
EVAL_SEED_PATH = REPO_ROOT / "evals" / "kg_expansion" / "seed.jsonl"


@lru_cache(maxsize=1)
def load_fewshot() -> dict:
    if not FEWSHOT_PATH.is_file():
        return {}
    with FEWSHOT_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def format_fewshot_for_prompt() -> str:
    data = load_fewshot()
    if not data:
        return ""
    return json.dumps(data, indent=2)


def load_eval_seed_rows() -> list[dict]:
    if not EVAL_SEED_PATH.is_file():
        return []
    rows: list[dict] = []
    with EVAL_SEED_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
