#!/usr/bin/env python3
"""Convert KPs CSV export to JSON catalog."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def convert(csv_path: Path, json_path: Path) -> dict:
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "source_kp_id": row["source_kp_id"].strip(),
                    "knowledge_node_id": row["knowledge_node_id"].strip(),
                    "label": row["label"].strip(),
                    "label_enum": row["label_enums"].strip(),
                    "description": row["description"].strip(),
                }
            )

    catalog = {
        "catalog_id": json_path.stem,
        "source_file": str(csv_path.name),
        "count": len(rows),
        "knowledge_points": rows,
    }

    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return catalog


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    default_csv = root / "curriculum" / "KPs-ProgrammingFoundations.csv"
    default_json = root / "curriculum" / "KPs-ProgrammingFoundations.json"

    parser = argparse.ArgumentParser(description="Convert KP CSV to JSON")
    parser.add_argument("--csv", type=Path, default=default_csv)
    parser.add_argument("--out", type=Path, default=default_json)
    args = parser.parse_args()

    catalog = convert(args.csv, args.out)
    print(f"Wrote {catalog['count']} knowledge points to {args.out}")


if __name__ == "__main__":
    main()
