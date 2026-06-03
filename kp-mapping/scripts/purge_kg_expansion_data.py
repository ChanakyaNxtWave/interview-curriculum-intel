#!/usr/bin/env python3
"""Delete all gap-expansion runs and proposed KP/node rows."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kp_mapping.kg_expansion.store import KgExpansionStore  # noqa: E402

DB = ROOT / "data" / "kp_mappings.db"


def main() -> None:
    store = KgExpansionStore(DB)
    counts = store.purge_all_data()
    print(json.dumps({"purged": counts, "db": str(DB)}, indent=2))


if __name__ == "__main__":
    main()
