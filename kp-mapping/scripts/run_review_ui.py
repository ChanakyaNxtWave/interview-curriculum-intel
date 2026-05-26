#!/usr/bin/env python3
"""Start the KP mapping human review UI."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from kp_mapping.env import load_env  # noqa: E402

load_env()


def main() -> None:
    import uvicorn

    os.environ.setdefault("KP_MAPPING_DB", str(ROOT / "data" / "kp_mappings.db"))
    os.environ.setdefault(
        "KP_CATALOG_JSON",
        str(REPO_ROOT / "curriculum" / "KPs-ProgrammingFoundations.json"),
    )
    uvicorn.run(
        "kp_mapping.server:app",
        host="0.0.0.0",
        port=int(os.environ.get("KP_REVIEW_PORT", "8765")),
        reload=False,
    )


if __name__ == "__main__":
    main()
