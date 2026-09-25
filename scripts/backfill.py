#!/usr/bin/env python3
"""CLI utility to run an incremental dlt backfill from the Elexon BMRS API into DuckDB."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import logging
from pathlib import Path
import sys
import time

import dlt
from power_desk.db import get_db
from power_desk.sources.bmrs import get_default_builder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")


def run_backfill(
    start_date: str = "2024-01-01",
    end_date: str | None = None,
    resources: list[str] | None = None,
    db_path: str = "data/warehouse.duckdb",
    dataset_name: str = "raw",
    refresh: str | None = None,
) -> None:
    end_display = end_date if end_date else "Until data ends (live horizon)"

    print(f"\n=======================================================")
    print(f"⚡ POWER DESK — Elexon BMRS Backfill")
    print(f"=======================================================")
    print(f"  • Start Date:    {start_date} (resumes from pointer if stored)")
    print(f"  • Target:        {end_display}")
    print(f"  • Destination:   DuckDB ({db_path})")
    print(f"  • Dataset/Schema:{dataset_name}")
    print(f"  • Incremental:   lag=0 (advances & stores latest pointer)")
    print(f"  • Strategy:      Incremental Merge on Natural Keys")
    if refresh:
        print(f"  • Refresh Mode:  {refresh}")
    print(f"=======================================================\n")

    builder = get_default_builder()
    all_available = list(builder.configs.keys())

    selected_resources = resources or all_available
    for r in selected_resources:
        if r not in builder.configs:
            print(f"Error: Unknown resource '{r}'. Available: {all_available}", file=sys.stderr)
            sys.exit(1)

    # Filter builder configs to only requested resources
    builder.configs = {k: v for k, v in builder.configs.items() if k in selected_resources}
    print(f"Selected Resources ({len(selected_resources)}): {', '.join(selected_resources)}")

    source = builder.build(
        source_name="bmrs_backfill",
        initial_date=start_date,
        end_date=end_date,
    )

    pipeline = dlt.pipeline(
        pipeline_name="bmrs_backfill",
        destination=dlt.destinations.duckdb(db_path),
        dataset_name=dataset_name,
    )

    # Abort any stale pending packages left behind by earlier failed runs
    try:
        pipeline.abort_packages()
    except Exception:
        pass

    t0 = time.perf_counter()
    print(f"\nStarting extraction and load (refresh={refresh})...")
    load_info = pipeline.run(source, refresh=refresh)  # type: ignore
    duration = round(time.perf_counter() - t0, 2)

    print(f"\n✓ Backfill completed in {duration}s!")
    print(load_info)

    # Refresh views in DuckDB
    print("\nRefreshing ODS and Marts views...")
    db = get_db()
    db.initialize()
    print("✓ All SQL views updated successfully.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run an incremental dlt backfill for UK power data into DuckDB"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-01-01",
        help="Initial backfill date (YYYY-MM-DD), supports back to 2021",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End backfill date (YYYY-MM-DD), defaults to today",
    )
    parser.add_argument(
        "--refresh",
        type=str,
        choices=["drop_sources", "drop_resources", "drop_data"],
        default=None,
        help="dlt native refresh mode: 'drop_sources' (drop tables & state), 'drop_resources', or 'drop_data'",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Perform a full refresh (alias for --refresh drop_sources)",
    )
    parser.add_argument(
        "--resources",
        type=str,
        nargs="+",
        help="List of resources to extract: raw_fuelinst, raw_indo, raw_itsdo, raw_demand_forecast, raw_windfor",
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

    args = parser.parse_args()
    refresh_mode = "drop_sources" if args.full_refresh else args.refresh

    run_backfill(
        start_date=args.start_date,
        end_date=args.end_date,
        resources=args.resources,
        db_path=args.db_path,
        dataset_name=args.dataset,
        refresh=refresh_mode,
    )


if __name__ == "__main__":
    main()
