#!/usr/bin/env python3
"""Print gap-expansion eval seed summary (gold vs anti-pattern rows)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kp_mapping.kg_expansion.evals import run_eval_seed_report  # noqa: E402
from kp_mapping.kg_expansion.fewshot import load_eval_seed_rows  # noqa: E402


def main() -> None:
    rows = load_eval_seed_rows()
    report = run_eval_seed_report(rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
