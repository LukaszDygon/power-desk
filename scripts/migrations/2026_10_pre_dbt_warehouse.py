#!/usr/bin/env python3
"""One-time migration of a pre-dbt warehouse (SQL views + `bmrs_backfill` pipeline).

1. Back up the DuckDB file (`<name>.pre-dbt.duckdb`).
2. Drop the legacy `raw.ods_*` / `raw.mart_*` views (now dbt models in `ods` / `marts`).
3. Seed the `bmrs` pipeline's incremental cursors from `bmrs_backfill`, so scheduled
   runs resume where the old loader stopped instead of re-fetching from the start date.
4. Optionally backfill `raw_pvlive_solar` (solar used to be injected into raw_fuelinst;
   those legacy rows are ignored by `ods_generation_actual`).
5. Run a full `dbt build` (all existing loads are pending on the first build).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from typing import Any

import dlt
import duckdb
from dlt.pipeline.state_sync import decompress_state

from power_desk.ingest.bmrs import get_default_builder
from power_desk.ingest.common import to_date
from power_desk.ingest.pipelines import make_pipeline, make_source, run_with_lock_retry, warehouse_path
from power_desk.transform import dbt_build_args, pending_load_ids, run_dbt

LEGACY_PIPELINE = "bmrs_backfill"


def legacy_state(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    row = con.execute(
        "select state from raw._dlt_pipeline_state where pipeline_name = ? order by version desc limit 1",
        [LEGACY_PIPELINE],
    ).fetchone()
    return decompress_state(row[0]) if row else {}


def seed_cursor_state(db_path: str, legacy: dict[str, Any]) -> list[str]:
    """Commit the legacy publishTime cursors as `bmrs` pipeline state (no data is loaded)."""
    old_resources = legacy.get("sources", {}).get(LEGACY_PIPELINE, {}).get("resources", {})
    seeded: list[str] = []

    def make_seeder(name: str, cursor_field: str, cursor_state: dict[str, Any]):
        def seeder():
            state = dlt.current.resource_state()
            state.setdefault("incremental", {})[cursor_field] = cursor_state
            state["last_window"] = {"last_day": to_date(cursor_state["last_value"]).isoformat(), "capped": False}
            yield from ()

        return dlt.resource(seeder, name=name)

    resources = []
    for name, config in get_default_builder().configs.items():
        cursor_state = old_resources.get(name, {}).get("incremental", {}).get(config.cursor_field)
        if cursor_state and cursor_state.get("last_value"):
            resources.append(make_seeder(name, config.cursor_field, cursor_state))
            seeded.append(f"{name}={cursor_state['last_value']}")

    if resources:
        @dlt.source(name="bmrs")
        def bmrs():
            return resources

        run_with_lock_retry(make_pipeline("bmrs", db_path=db_path), bmrs())
    return seeded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--backfill-pvlive", action="store_true",
                        help="Load PVLive solar from the start date to today in one run")
    parser.add_argument("--skip-dbt", action="store_true")
    args = parser.parse_args()

    db_path = args.db_path or str(warehouse_path())
    if not args.no_backup:
        backup = db_path.replace(".duckdb", ".pre-dbt.duckdb")
        shutil.copy(db_path, backup)
        print(f"Backup written to {backup}")

    con = duckdb.connect(db_path)
    legacy_views = [r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema = 'raw' and table_type = 'VIEW' "
        "and (table_name like 'ods\\_%' escape '\\' or table_name like 'mart\\_%' escape '\\')"
    ).fetchall()]
    for view in legacy_views:
        con.execute(f"drop view raw.{view}")
    print(f"Dropped legacy views: {legacy_views}")
    has_bmrs_state = con.execute(
        "select count(*) from raw._dlt_pipeline_state where pipeline_name = 'bmrs'"
    ).fetchone()[0]
    legacy = legacy_state(con)
    con.close()

    if has_bmrs_state:
        print("`bmrs` pipeline state already exists; cursors left as they are.")
    else:
        print(f"Seeded bmrs cursors: {seed_cursor_state(db_path, legacy)}")

    if args.backfill_pvlive:
        info = run_with_lock_retry(make_pipeline("pvlive", db_path=db_path), make_source("pvlive", max_days_per_run=10_000))
        print(info)

    if args.skip_dbt:
        return 0
    return run_dbt(dbt_build_args(pending_load_ids(db_path)), db_path=db_path)


if __name__ == "__main__":
    sys.exit(main())
