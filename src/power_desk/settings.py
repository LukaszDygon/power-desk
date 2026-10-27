"""Environment and file locations, read from environment variables (and `.env` at the repo root).

| Variable | Default | |
|---|---|---|
| `POWER_DESK_ENV` | `dev` | `dev` or `prod`: selects warehouse, dbt target, dlt state and Dagster instance |
| `POWER_DESK_DUCKDB_PATH` | `data/warehouse_<env>.duckdb` | warehouse file |
| `POWER_DESK_PIPELINES_DIR` | `.dlt/pipelines/<env>` | dlt working directory (disposable) |
| `POWER_DESK_START_DATE` | `2024-01-01` | first date the warehouse must cover |
| `POWER_DESK_DBT_MANIFEST` | `transform/target/manifest.json` | dbt manifest read by the dashboard and catalogue |
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = REPO_ROOT / "transform"
DATA_DIR = REPO_ROOT / "data"
ENVIRONMENTS = ("dev", "prod")

load_dotenv(REPO_ROOT / ".env", override=False)


def environment() -> str:
    env = os.environ.get("POWER_DESK_ENV", "dev")
    if env not in ENVIRONMENTS:
        raise ValueError(f"POWER_DESK_ENV={env!r}; expected one of {ENVIRONMENTS}")
    return env


def warehouse_path() -> Path:
    """The DuckDB warehouse; its file name is also the catalog name dbt bakes into views."""
    path = Path(os.environ.get("POWER_DESK_DUCKDB_PATH") or f"data/warehouse_{environment()}.duckdb")
    return path if path.is_absolute() else REPO_ROOT / path


def pipelines_dir() -> Path:
    return Path(os.environ.get("POWER_DESK_PIPELINES_DIR") or REPO_ROOT / ".dlt" / "pipelines" / environment())


def dagster_home() -> Path:
    return Path(os.environ.get("DAGSTER_HOME") or REPO_ROOT / ".dagster" / environment())


def backfill_start_date() -> str:
    return os.environ.get("POWER_DESK_START_DATE") or "2024-01-01"


def dbt_manifest_path() -> Path:
    return Path(os.environ.get("POWER_DESK_DBT_MANIFEST") or DBT_PROJECT_DIR / "target" / "manifest.json")
