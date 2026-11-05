"""Load the seed week through every source's pipeline (replayed publishers), then build dbt."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys

from power_desk_elt.ingest.pipeline import working_dir
from power_desk_elt.ingest.seed.load import load_seed
from power_desk_elt.ingest.seed.replay import SEED_START
from power_desk_elt.settings import environment, warehouse_path
from power_desk_elt.transform.dbt import DbtRun
import power_desk_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None, help="warehouse file (default: POWER_DESK_DUCKDB_PATH)")
    parser.add_argument("--skip-dbt", action="store_true", help="only load raw tables")
    parser.add_argument("--force", action="store_true", help="allow loading seed data into prod")
    parser.add_argument("--fresh", action="store_true", help="delete the warehouse file and its dlt state first")
    args = parser.parse_args()
    power_desk_logging.configure("load-seed")
    if environment() == "prod" and not (args.db_path or args.force):
        parser.error("refusing to load seed data into the prod warehouse; use POWER_DESK_ENV=dev or --force")

    db_path = args.db_path or str(warehouse_path())
    if args.fresh:  # e.g. after raw columns change, when old tables or dlt state would break the load
        for path in (Path(db_path), Path(f"{db_path}.wal")):
            path.unlink(missing_ok=True)
        shutil.rmtree(working_dir(db_path), ignore_errors=True)
    os.environ.setdefault("POWER_DESK_START_DATE", SEED_START)
    load_seed(db_path)  # logs a `dlt.load` event per load
    return 0 if args.skip_dbt else DbtRun().run(db_path)


if __name__ == "__main__":
    sys.exit(main())
