#!/usr/bin/env python3
"""Load the curated 7-day seed dataset into DuckDB via dlt, then build the dbt project."""

from __future__ import annotations

import argparse
import os
import sys
import time

from power_desk.ingest.pipelines import environment, warehouse_path
from power_desk.ingest.seed import generate_seed_data, load_seed
from power_desk.transform import dbt_build_args, pending_load_ids, run_dbt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None, help="DuckDB warehouse (default: POWER_DESK_DUCKDB_PATH)")
    parser.add_argument("--generate", action="store_true", help="Regenerate the seed parquet files first")
    parser.add_argument("--skip-dbt", action="store_true", help="Only load raw tables")
    parser.add_argument("--force", action="store_true", help="Allow loading synthetic seed data into prod")
    args = parser.parse_args()

    if environment() == "prod" and not (args.db_path or args.force):
        parser.error("refusing to load synthetic seed data into the prod warehouse; use POWER_DESK_ENV=dev or --force")
    db_path = args.db_path or str(warehouse_path())
    # The seed covers 2024-03-01..07; completeness tests start from POWER_DESK_START_DATE.
    os.environ.setdefault("POWER_DESK_START_DATE", "2024-03-01")

    if args.generate:
        print(f"Generated seed parquet: {generate_seed_data()}")

    t0 = time.perf_counter()
    print(load_seed(db_path))
    print(f"✓ Seed loaded into {db_path} in {time.perf_counter() - t0:.1f}s")

    if args.skip_dbt:
        return 0
    return run_dbt(dbt_build_args(pending_load_ids(db_path)), db_path=db_path)


if __name__ == "__main__":
    sys.exit(main())
