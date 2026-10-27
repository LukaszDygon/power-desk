#!/usr/bin/env python3
"""Run dlt ingestion, then `dbt build`, outside Dagster.

Without dates each source resumes from its cursor; `--start-date`/`--end-date` run a bounded
backfill that leaves the cursor untouched; `--chunk-days` loads a long range chunk by chunk.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import logging
import sys
from typing import Iterator

from power_desk.ingest.pipelines import PIPELINES, make_pipeline, make_source, run_with_lock_retry, warehouse_path
from power_desk.transform import dbt_build_args, pending_load_ids, run_dbt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def date_chunks(start: str, end: str, days: int) -> Iterator[tuple[str, str]]:
    """Inclusive (start, end) date windows of at most `days` days."""
    curr, last = date.fromisoformat(start), date.fromisoformat(end)
    while curr <= last:
        chunk_end = min(curr + timedelta(days=days - 1), last)
        yield curr.isoformat(), chunk_end.isoformat()
        curr = chunk_end + timedelta(days=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pipelines", nargs="+", choices=sorted(PIPELINES), default=sorted(PIPELINES))
    parser.add_argument("--resources", nargs="+", help="Subset of resources (raw table names)")
    parser.add_argument("--start-date", help="Initial cursor when no state exists (default POWER_DESK_START_DATE)")
    parser.add_argument("--end-date", help="Inclusive end date for a bounded backfill")
    parser.add_argument("--max-days", type=int, help="Max days fetched per pipeline in an open-ended run")
    parser.add_argument("--chunk-days", type=int,
                        help="Bounded backfill in chunks of N days, each loaded (and committed) separately")
    parser.add_argument("--refresh", choices=["drop_sources", "drop_resources", "drop_data"])
    parser.add_argument("--full-refresh", action="store_true", help="Alias for --refresh drop_sources")
    parser.add_argument("--db-path", default=None, help="DuckDB warehouse (default: POWER_DESK_DUCKDB_PATH)")
    parser.add_argument("--scope", choices=["recent", "all"], default=None,
                        help="dbt test scope (default: all for bounded backfills, else recent)")
    parser.add_argument("--skip-dbt", action="store_true")
    args = parser.parse_args()

    db_path = args.db_path or str(warehouse_path())
    refresh = "drop_sources" if args.full_refresh else args.refresh

    if args.chunk_days and not (args.start_date and args.end_date):
        parser.error("--chunk-days needs --start-date and --end-date")
    if args.chunk_days and refresh:
        parser.error("--chunk-days cannot be combined with a refresh mode")
    windows = (
        list(date_chunks(args.start_date, args.end_date, args.chunk_days))
        if args.chunk_days
        else [(args.start_date, args.end_date)]
    )

    for name in args.pipelines:
        resources = [r for r in args.resources or [] if r in make_source(name).resources] or None
        if args.resources and not resources:
            continue
        pipeline = make_pipeline(name, db_path=db_path)
        for i, (start, end) in enumerate(windows, 1):
            if len(windows) > 1:
                logging.info("%s chunk %s/%s: %s..%s", name, i, len(windows), start, end)
            source = make_source(name, start, end, args.max_days, resources)
            print(run_with_lock_retry(pipeline, source, **({"refresh": refresh} if refresh else {})))

    if args.skip_dbt:
        return 0
    scope = args.scope or ("all" if args.end_date else "recent")
    return run_dbt(dbt_build_args(pending_load_ids(db_path), scope=scope, full_refresh=bool(refresh)), db_path=db_path)


if __name__ == "__main__":
    sys.exit(main())
