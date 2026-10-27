"""One Dagster asset per dlt resource (`raw/<source>__<dataset>`), one multi-asset per source.

Each materialization records the run's dlt load ids and, for open-ended runs, the resource's
cursor, last window and whether it was capped (read by the catch-up sensor and lag checks).
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from dagster import AssetExecutionContext, AssetKey, Config, MaterializeResult
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData
import dlt

from power_desk.ingest.pipeline import DATASET_NAME, make_pipeline, make_source, resource_progress
from power_desk.ingest.registry import SOURCES
from power_desk.ingest.spec import RunWindow
from power_desk.orchestration.warehouse_lock import WAREHOUSE_POOL, retry_run_if_locked


class RawTableTranslator(DagsterDltTranslator):
    """dlt resource -> asset `raw/<resource>`, the key the dbt sources declare (`meta.dagster.asset_key`)."""

    def get_asset_spec(self, data: DltResourceTranslatorData):
        spec = super().get_asset_spec(data)
        source = data.pipeline.pipeline_name if data.pipeline else "api"
        return spec.replace_attributes(
            key=AssetKey([DATASET_NAME, data.resource.name]),
            group_name=DATASET_NAME,
            deps=[AssetKey(["api", source, data.resource.name])],
        )


class IngestConfig(Config):
    start_date: str | None = None  # initial cursor when no state exists (default POWER_DESK_START_DATE)
    end_date: str | None = None  # bounded backfill: inclusive end date, leaves the cursor untouched
    max_days_per_run: int | None = None
    refresh: str | None = None  # dlt refresh mode: drop_sources | drop_resources | drop_data


def minutes_behind(cursor: Any, now: datetime | None = None) -> float | None:
    if not cursor:
        return None
    value = cursor if isinstance(cursor, datetime) else datetime.fromisoformat(str(cursor).replace("Z", "+00:00"))
    value = value if value.tzinfo else value.replace(tzinfo=UTC)
    return round(((now or datetime.now(UTC)) - value).total_seconds() / 60, 1)


def load_metadata(pipeline: dlt.Pipeline, window: RunWindow) -> dict[str, Any]:
    """The run's dlt loads."""
    load_info = pipeline.last_trace.last_load_info if pipeline.last_trace else None
    return {
        "dlt_load_ids": list(load_info.loads_ids) if load_info else [],
        "dlt_pipeline": pipeline.pipeline_name,
        "bounded_backfill": window.bounded,
    }


def progress_metadata(progress: dict[str, Any]) -> dict[str, Any]:
    """An open-ended run's progress: cursor, lag, window and whether it was capped."""
    lag = minutes_behind(progress.get("cursor_last_value"))
    return {
        "cursor_last_value": str(progress.get("cursor_last_value") or ""),
        "window_capped": bool(progress.get("capped", False)),
        "window": f"{progress.get('first_day', '')}..{progress.get('last_day', '')}",
        **({"cursor_lag_minutes": lag} if lag is not None else {}),
        **{k: str(v) for k, v in progress.items() if k.startswith("source_") and v is not None},
    }


def source_assets(name: str):
    @dlt_assets(
        dlt_source=make_source(name),
        dlt_pipeline=make_pipeline(name),
        name=f"{name}_ingest",
        dagster_dlt_translator=RawTableTranslator(),
        pool=WAREHOUSE_POOL,
    )
    def ingest(context: AssetExecutionContext, dlt: DagsterDltResource, config: IngestConfig) -> Iterator[Any]:
        pipeline = make_pipeline(name)
        window = SOURCES[name].window(config.start_date, config.end_date, config.max_days_per_run)
        source = make_source(name, window)
        try:
            results = list(dlt.run(context=context, dlt_source=source, dlt_pipeline=pipeline, refresh=config.refresh))
        except Exception as exc:
            retry_run_if_locked(exc)
            raise
        for result in results:
            assert result.asset_key is not None  # dagster-dlt materializes one asset per resource
            progress = resource_progress(pipeline, source.name).get(result.asset_key.path[-1], {})
            metadata = {**(result.metadata or {}), **load_metadata(pipeline, window)}
            if not window.bounded:
                metadata |= progress_metadata(progress)
            yield MaterializeResult(asset_key=result.asset_key, metadata=metadata)

    return ingest


DLT_ASSETS = [source_assets(name) for name in SOURCES]
