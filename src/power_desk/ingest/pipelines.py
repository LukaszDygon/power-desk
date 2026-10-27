"""Source registry and dlt pipeline factories shared by Dagster, the CLI scripts and tests.

All pipelines load into the `raw` dataset of the DuckDB warehouse; table names must be
unique across sources (prefix them with the source name when in doubt). Incremental
state is persisted by dlt in `raw._dlt_pipeline_state` and restored from there, so the
local working directory (`.dlt/pipelines`) is disposable.

To add a source: implement `ingest/<source>.py` with a `SPEC` (see `ingest/common.py`)
and append it to `SOURCES`.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging
import os
from pathlib import Path
import time
from typing import Any

import dlt
from dlt.common.pipeline import LoadInfo
from dlt.sources import DltSource

from power_desk.ingest import bmrs, entsoe_eic, pvlive
from power_desk.ingest.common import SourceSpec

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
DATASET_NAME = "raw"


ENVIRONMENTS = ("dev", "prod")


def environment() -> str:
    """Active environment (`POWER_DESK_ENV`: dev | prod, default dev); selects warehouse, dbt target and dlt state."""
    env = os.environ.get("POWER_DESK_ENV", "dev")
    if env not in ENVIRONMENTS:
        raise ValueError(f"POWER_DESK_ENV={env!r}; expected one of {ENVIRONMENTS}")
    return env


def warehouse_path() -> Path:
    """DuckDB warehouse: `POWER_DESK_DUCKDB_PATH` if set, else `data/warehouse_<env>.duckdb`.

    Relative paths resolve against the repo root. The file name is also the DuckDB catalog
    name that dbt bakes into view definitions, so rebuild with `dbt build` after renaming it.
    """
    path = Path(os.environ.get("POWER_DESK_DUCKDB_PATH") or f"data/warehouse_{environment()}.duckdb")
    return path if path.is_absolute() else REPO_ROOT / path


def pipelines_dir() -> Path:
    """dlt working directory per environment (`POWER_DESK_PIPELINES_DIR`); disposable, state is restored from the warehouse."""
    return Path(os.environ.get("POWER_DESK_PIPELINES_DIR") or REPO_ROOT / ".dlt" / "pipelines" / environment())


def backfill_start_date() -> str:
    """First date the warehouse must cover (`POWER_DESK_START_DATE`)."""
    return os.environ.get("POWER_DESK_START_DATE") or "2024-01-01"


SOURCES: tuple[SourceSpec, ...] = (bmrs.SPEC, pvlive.SPEC, entsoe_eic.SPEC)
PIPELINES: dict[str, SourceSpec] = {spec.name: spec for spec in SOURCES}


def make_pipeline(name: str, db_path: Path | str | None = None, export_schema: bool = True) -> dlt.Pipeline:
    """Create the dlt pipeline `name` targeting the warehouse.

    With `export_schema`, dlt writes the inferred schema to `ingest/schemas/` after
    each run; those committed files feed the generated dbt sources (catalogue).
    `POWER_DESK_EXPORT_SCHEMAS=0` disables the export (tests).
    """
    export = export_schema and os.environ.get("POWER_DESK_EXPORT_SCHEMAS", "1") != "0"
    return dlt.pipeline(
        pipeline_name=name,
        destination=dlt.destinations.duckdb(str(db_path or warehouse_path())),
        dataset_name=DATASET_NAME,
        pipelines_dir=str(pipelines_dir()),
        export_schema_path=str(SCHEMAS_DIR) if export else None,
    )


def make_source(
    name: str,
    start_date: str | None = None,
    end_date: str | None = None,
    max_days_per_run: int | None = None,
    resources: list[str] | None = None,
) -> DltSource:
    """Source covering dates `start_date`..`end_date` (inclusive), padded per the source spec."""
    spec = PIPELINES[name]
    pad = timedelta(days=spec.window_padding_days)
    start = date.fromisoformat((start_date or backfill_start_date())[:10]) - pad
    end = date.fromisoformat(end_date[:10]) + pad if end_date else None
    source = spec.build_source(
        initial_date=start.isoformat(),
        end_date=end.isoformat() if end else None,
        max_days_per_run=max_days_per_run if max_days_per_run is not None else spec.max_days_per_run,
    )
    if resources:
        source = source.with_resources(*resources)
    return source


def run_with_lock_retry(pipeline: dlt.Pipeline, source: DltSource, retries: int = 6, **kwargs: Any) -> LoadInfo:
    """Run a pipeline, retrying while a dashboard reader holds the DuckDB file lock."""
    for attempt in range(1, retries + 1):
        try:
            return pipeline.run(source, **kwargs)
        except Exception as exc:
            if "lock" not in str(exc).lower() or attempt == retries:
                raise
            logger.warning("DuckDB file locked (attempt %s/%s), retrying in 1.5s", attempt, retries)
            pipeline.drop_pending_packages()
            time.sleep(1.5)
    raise AssertionError("unreachable")


def window_state(pipeline: dlt.Pipeline, source_name: str) -> dict[str, dict[str, Any]]:
    """Per-resource cursor and last fetch window from pipeline state (for orchestration metadata)."""
    resources = pipeline.state.get("sources", {}).get(source_name, {}).get("resources", {})
    out: dict[str, dict[str, Any]] = {}
    for resource_name, state in resources.items():
        cursors = state.get("incremental", {})
        last_value = next((c.get("last_value") for c in cursors.values() if c.get("last_value")), None)
        out[resource_name] = {
            "cursor_last_value": last_value,
            **state.get("last_window", {}),
            **{f"source_{k}": v for k, v in state.get("source_file", {}).items()},
        }
    return out
