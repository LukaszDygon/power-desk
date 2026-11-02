"""ELT environment and file locations, read from environment variables (and `.env` at the repo root).

The warehouse's own (`POWER_DESK_ENV`, `POWER_DESK_DUCKDB_PATH`, `POWER_DESK_DBT_MANIFEST`) are shared with
its readers in `power_desk_warehouse.settings`, and re-exported here.

| Variable | Default | |
|---|---|---|
| `POWER_DESK_PIPELINES_DIR` | `.dlt/pipelines/<env>` | dlt working directory (disposable) |
| `POWER_DESK_START_DATE` | `2024-01-01` | first date the warehouse must cover |
| `DAGSTER_HOME` | `elt/.dagster/<env>` | Dagster instance |
"""

from __future__ import annotations

import os
from pathlib import Path

from power_desk_warehouse.settings import DATA_DIR, REPO_ROOT, dbt_manifest_path, environment, warehouse_path

__all__ = [
    "DATA_DIR",
    "DBT_PROJECT_DIR",
    "ELT_ROOT",
    "REPO_ROOT",
    "SEED_DIR",
    "backfill_start_date",
    "dagster_home",
    "dbt_manifest_path",
    "environment",
    "pipelines_dir",
    "warehouse_path",
]

ELT_ROOT = Path(__file__).resolve().parents[2]
# its target/manifest.json is the default of dbt_manifest_path()
DBT_PROJECT_DIR = ELT_ROOT / "dbt"
SEED_DIR = ELT_ROOT / "seed"


def pipelines_dir() -> Path:
    return Path(os.environ.get("POWER_DESK_PIPELINES_DIR") or REPO_ROOT / ".dlt" / "pipelines" / environment())


def dagster_home() -> Path:
    return Path(os.environ.get("DAGSTER_HOME") or ELT_ROOT / ".dagster" / environment())


def backfill_start_date() -> str:
    return os.environ.get("POWER_DESK_START_DATE") or "2024-01-01"
