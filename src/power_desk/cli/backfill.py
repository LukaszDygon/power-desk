"""Run dlt ingestion, then dbt, outside Dagster.

Without dates each source resumes from its cursor; `--start-date`/`--end-date` run a bounded
backfill that leaves the cursor untouched; `--chunk-days` loads a long range chunk by chunk.
"""

from __future__ import annotations

import argparse
import logging
import sys

from power_desk.ingest.pipeline import make_pipeline, make_source, run
from power_desk.ingest.registry import SOURCES
from power_desk.ingest.spec import RunWindow, SourceSpec
from power_desk.ingest.windows import DateRange, to_date
from power_desk.settings import warehouse_path
from power_desk.transform.dbt import DbtRun


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCES), default=sorted(SOURCES))
    parser.add_argument("--resources", nargs="+", help="only these raw tables")
    parser.add_argument("--start-date", help="initial cursor when no state exists (default POWER_DESK_START_DATE)")
    parser.add_argument("--end-date", help="inclusive end date of a bounded backfill")
    parser.add_argument("--max-days", type=int, help="max days fetched per source in an open-ended run")
    parser.add_argument(
        "--chunk-days", type=int, help="bounded backfill in chunks of N days, each committed separately"
    )
    parser.add_argument("--refresh", choices=["drop_sources", "drop_resources", "drop_data"], help="dlt refresh mode")
    parser.add_argument("--db-path", default=None, help="warehouse file (default: POWER_DESK_DUCKDB_PATH)")
    parser.add_argument("--scope", choices=["recent", "all"], help="dbt test scope (default: all when bounded)")
    parser.add_argument("--skip-dbt", action="store_true")
    args = parser.parse_args()
    if args.chunk_days and not (args.start_date and args.end_date):
        parser.error("--chunk-days needs --start-date and --end-date")
    if args.chunk_days and args.refresh:
        parser.error("--chunk-days cannot be combined with --refresh")
    return args


def run_windows(args: argparse.Namespace, spec: SourceSpec) -> list[RunWindow]:
    """The requested window, or its `--chunk-days` chunks."""
    if not args.chunk_days:
        return [spec.window(args.start_date, args.end_date, args.max_days)]
    requested = DateRange(to_date(args.start_date), to_date(args.end_date))
    return [spec.window(chunk.first, chunk.last, args.max_days) for chunk in requested.chunks(args.chunk_days)]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    db_path = args.db_path or str(warehouse_path())
    for name in args.sources:
        resources = [r for r in args.resources or [] if r in make_source(name).resources] or None
        if args.resources and not resources:
            continue
        pipeline = make_pipeline(name, db_path)
        for window in run_windows(args, SOURCES[name]):
            print(run(pipeline, make_source(name, window, resources), refresh=args.refresh))
    if args.skip_dbt:
        return 0
    scope = args.scope or ("all" if args.end_date else "recent")
    return DbtRun(scope=scope, full_refresh=bool(args.refresh)).run_pending(db_path)


if __name__ == "__main__":
    sys.exit(main())
