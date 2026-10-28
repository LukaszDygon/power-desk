"""dlt pipelines into the warehouse's `raw` dataset.

Raw tables (dlt resources) are named `<source>__<dataset>`, like their staging models
`stg_<source>__<dataset>`. dlt keeps pipeline state in `raw._dlt_pipeline_state` and restores it
from there, so the local working directory is disposable. Each run exports the dlt schema to
`ingest/schemas/`, which defines the dbt sources (`POWER_DESK_EXPORT_SCHEMAS=0` disables it).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import dlt
from dlt.common.pipeline import LoadInfo
from dlt.sources import DltSource
from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_delay, wait_fixed

from power_desk.ingest.registry import SOURCES
from power_desk.ingest.spec import RunWindow
from power_desk.settings import pipelines_dir, warehouse_path
from power_desk.warehouse import is_lock_error

logger = logging.getLogger(__name__)

DATASET_NAME = "raw"
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


def make_pipeline(name: str, db_path: Path | str | None = None, schemas_dir: Path | None = SCHEMAS_DIR) -> dlt.Pipeline:
    """Pipeline `name` into the warehouse; it exports its schema to `schemas_dir` unless that is None."""
    if os.environ.get("POWER_DESK_EXPORT_SCHEMAS", "1") == "0":
        schemas_dir = None
    return dlt.pipeline(
        pipeline_name=name,
        destination=dlt.destinations.duckdb(str(db_path or warehouse_path())),
        dataset_name=DATASET_NAME,
        pipelines_dir=str(pipelines_dir()),
        # dlt annotates this optional parameter as `str`
        export_schema_path=str(schemas_dir) if schemas_dir else None,  # pyright: ignore[reportArgumentType]
    )


def make_source(name: str, window: RunWindow | None = None, resources: list[str] | None = None) -> DltSource:
    """Source `name` for `window` (default: open-ended from `POWER_DESK_START_DATE`), padded as the source needs."""
    spec = SOURCES[name]
    source = spec.build((window or spec.window()).padded(spec.window_padding_days))
    return source.with_resources(*resources) if resources else source


def run(pipeline: dlt.Pipeline, source: DltSource, **kwargs: Any) -> LoadInfo:
    """`pipeline.run`, retried for up to 7.5 s while a reader holds the warehouse lock."""

    def drop_partial_load(_: RetryCallState) -> None:
        logger.warning("warehouse locked, retrying")
        pipeline.drop_pending_packages()

    retry = Retrying(
        retry=retry_if_exception(is_lock_error),
        stop=stop_after_delay(7.5),
        wait=wait_fixed(1.5),
        before_sleep=drop_partial_load,
        reraise=True,
    )
    return retry(pipeline.run, source, **kwargs)


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
