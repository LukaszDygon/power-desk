"""Load the seed week through every source's pipeline (replayed publishers), then build dbt."""

from __future__ import annotations

import argparse
import os
import sys

from power_desk.ingest.seed.load import load_seed
from power_desk.ingest.seed.replay import SEED_START
from power_desk.settings import environment, warehouse_path
from power_desk.transform.dbt import dbt_args, run_dbt
from power_desk.transform.loads import pending_load_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None, help="warehouse file (default: POWER_DESK_DUCKDB_PATH)")
    parser.add_argument("--skip-dbt", action="store_true", help="only load raw tables")
    parser.add_argument("--force", action="store_true", help="allow loading seed data into prod")
    args = parser.parse_args()
    if environment() == "prod" and not (args.db_path or args.force):
        parser.error("refusing to load seed data into the prod warehouse; use POWER_DESK_ENV=dev or --force")

    db_path = args.db_path or str(warehouse_path())
    os.environ.setdefault("POWER_DESK_START_DATE", SEED_START)
    for info in load_seed(db_path):
        print(info)
    return 0 if args.skip_dbt else run_dbt(dbt_args(pending_load_ids(db_path)), db_path)


if __name__ == "__main__":
    sys.exit(main())
