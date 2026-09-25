#!/usr/bin/env python3
"""CLI utility to load curated seed parquet data into DuckDB via dlt."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

# Ensure project root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from power_desk.db import get_db, load_seed_with_dlt


def main():
    parser = argparse.ArgumentParser(
        description="Load curated UK power seed data into DuckDB warehouse via dlt"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/warehouse.duckdb",
        help="Path to DuckDB warehouse file",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="raw",
        help="DuckDB schema/dataset name (default: raw)",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Regenerate seed parquet files from generator first",
    )

    args = parser.parse_args()

    print("\n=======================================================")
    print("🌱 POWER DESK — Load Seed Data Task")
    print("=======================================================")
    print(f"  • Destination: DuckDB ({args.db_path})")
    print(f"  • Schema:      {args.dataset}")
    print("=======================================================\n")

    if args.generate:
        print("Generating realistic 7-day seed parquet files...")
        from power_desk.seed import generate_seed_data
        counts = generate_seed_data()
        print(f"✓ Seed parquet generated: {counts}\n")

    print("Loading seed parquet datasets into DuckDB via dlt...")
    t0 = time.perf_counter()
    load_seed_with_dlt(args.db_path, dataset_name=args.dataset)
    duration = round(time.perf_counter() - t0, 2)
    print(f"✓ Seed data loaded in {duration}s")

    print("\nRegistering ODS and Marts views...")
    db = get_db()
    db.initialize_views()
    print("✓ All SQL views created successfully.\n")


if __name__ == "__main__":
    main()
