"""dlt pipelines into the warehouse's `raw` dataset.

Raw tables (dlt resources) are named `<source>__<dataset>`, like their staging models
`stg_<source>__<dataset>`. dlt keeps pipeline state in `raw._dlt_pipeline_state` and restores it
from there, so the local working directory is disposable. Each run exports the dlt schema to
`ingest/schemas/`, which defines the dbt sources (`POWER_DESK_EXPORT_SCHEMAS=0` disables it).
Arrow tables (bulk file sources) get the same lineage columns (`_dlt_load_id`, `_dlt_id`) as JSON rows.
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

from power_desk.ingest.registry import SOURCES
from power_desk.settings import backfill_start_date, pipelines_dir, warehouse_path
from power_desk.warehouse import is_lock_error

logger = logging.getLogger(__name__)

DATASET_NAME = "raw"
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

dlt.config["normalize.parquet_normalizer.add_dlt_load_id"] = True
dlt.config["normalize.parquet_normalizer.add_dlt_id"] = True


def make_pipeline(name: str, db_path: Path | str | None = None, export_schema: bool = True) -> dlt.Pipeline:
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
    """Source `name` for `start_date`..`end_date` (inclusive; open-ended without `end_date`)."""
    spec = SOURCES[name]
    padding = timedelta(days=spec.window_padding_days)
    start = date.fromisoformat((start_date or backfill_start_date())[:10]) - padding
    end = date.fromisoformat(end_date[:10]) + padding if end_date else None
    source = spec.build(
        initial_date=start.isoformat(),
        end_date=end.isoformat() if end else None,
        max_days_per_run=spec.max_days_per_run if max_days_per_run is None else max_days_per_run,
    )
    return source.with_resources(*resources) if resources else source


def run(pipeline: dlt.Pipeline, source: DltSource, retries: int = 6, **kwargs: Any) -> LoadInfo:
    """`pipeline.run`, retried while a reader holds the warehouse lock."""
    for attempt in range(1, retries + 1):
        try:
            return pipeline.run(source, **kwargs)
        except Exception as exc:
            if not is_lock_error(exc) or attempt == retries:
                raise
            logger.warning("warehouse locked (attempt %s/%s), retrying", attempt, retries)
            pipeline.drop_pending_packages()
            time.sleep(1.5)
    raise AssertionError("unreachable")


def resource_progress(pipeline: dlt.Pipeline, source_name: str) -> dict[str, dict[str, Any]]:
    """Per resource: cursor, last window (`first_day`, `last_day`, `capped`) and snapshot file validators."""
    resources = pipeline.state.get("sources", {}).get(source_name, {}).get("resources", {})
    return {name: _progress(state) for name, state in resources.items()}


def _progress(state: dict[str, Any]) -> dict[str, Any]:
    cursors = state.get("incremental", {}).values()
    return {
        "cursor_last_value": next((c["last_value"] for c in cursors if c.get("last_value")), None),
        **state.get("last_window", {}),
        **{f"source_{key}": value for key, value in state.get("source_file", {}).items()},
    }
