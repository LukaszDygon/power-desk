"""Dagster assets: one asset per dlt resource (raw tables) and one per dbt node.

dlt assets attach the run's load ids and cursor/window state to each materialization;
the dbt asset passes the pending load ids to `dbt build --vars`.
"""


from datetime import UTC, datetime
import json
import os
from typing import Any, Iterator, Mapping

from dagster import (
    AssetExecutionContext,
    AssetKey,
    Config,
    MaterializeResult,
    RetryRequested,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData
import dlt
import duckdb

from power_desk.ingest.pipelines import DATASET_NAME, SOURCES, make_pipeline, make_source, warehouse_path, window_state
from power_desk.transform import DBT_EXECUTABLE, DBT_PROJECT_DIR, dbt_build_args, pending_load_ids, run_dbt

WAREHOUSE_POOL = "duckdb_warehouse"

# dbt reads the warehouse location from the environment (transform/profiles.yml).
os.environ.setdefault("POWER_DESK_DUCKDB_PATH", str(warehouse_path()))
# dagster-dbt resolves `dbt` from PATH (also for `dbt parse` in dev); use the venv's dbt-oss.
if str(DBT_EXECUTABLE.parent) not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = os.pathsep.join([str(DBT_EXECUTABLE.parent), os.environ.get("PATH", "")])

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()


def is_lock_error(error: "BaseException | str | None") -> bool:
    text = str(error or "").lower()
    return "could not set lock" in text or "conflicting lock" in text


class RawTableTranslator(DagsterDltTranslator):
    """dlt resource `raw_x` -> asset `raw/raw_x`, matching `meta.dagster.asset_key` in the dbt sources."""

    def get_asset_spec(self, data: DltResourceTranslatorData):
        spec = super().get_asset_spec(data)
        source_name = data.pipeline.pipeline_name if data.pipeline else "api"
        return spec.replace_attributes(
            key=AssetKey([DATASET_NAME, data.resource.name]),
            group_name=DATASET_NAME,
            deps=[AssetKey(["api", source_name, data.resource.name])],
        )


class IngestConfig(Config):
    start_date: str | None = None  # initial cursor value when no state exists (default POWER_DESK_START_DATE)
    end_date: str | None = None  # bounded backfill: inclusive end date, leaves the stored cursor untouched
    max_days_per_run: int | None = None
    refresh: str | None = None  # dlt refresh mode: drop_sources | drop_resources | drop_data


def cursor_lag_minutes(cursor: Any, now: datetime | None = None) -> float | None:
    if not cursor:
        return None
    value = cursor if isinstance(cursor, datetime) else datetime.fromisoformat(str(cursor).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return round(((now or datetime.now(UTC)) - value).total_seconds() / 60, 1)


def load_metadata(pipeline: dlt.Pipeline, source_name: str, resource: str, bounded: bool) -> dict[str, Any]:
    """dlt lineage + cursor metadata attached to a raw asset materialization."""
    load_info = pipeline.last_trace.last_load_info if pipeline.last_trace else None
    meta: dict[str, Any] = {
        "dlt_load_ids": list(load_info.loads_ids) if load_info else [],
        "dlt_pipeline": pipeline.pipeline_name,
        "bounded_backfill": bounded,
    }
    if not bounded:
        state = window_state(pipeline, source_name).get(resource, {})
        meta["cursor_last_value"] = str(state.get("cursor_last_value") or "")
        meta["window_capped"] = bool(state.get("capped", False))
        meta["window"] = f"{state.get('first_day', '')}..{state.get('last_day', '')}"
        lag = cursor_lag_minutes(state.get("cursor_last_value"))
        if lag is not None:
            meta["cursor_lag_minutes"] = lag
        # snapshot sources: which published file version was checked / loaded
        meta.update({k: str(v) for k, v in state.items() if k.startswith("source_") and v is not None})
    return meta


def make_dlt_assets(name: str):
    @dlt_assets(
        dlt_source=make_source(name),
        dlt_pipeline=make_pipeline(name),
        name=f"{name}_ingest",
        dagster_dlt_translator=RawTableTranslator(),
        pool=WAREHOUSE_POOL,
    )
    def _ingest(context: AssetExecutionContext, dlt: DagsterDltResource, config: IngestConfig) -> Iterator[Any]:
        pipeline = make_pipeline(name)
        source = make_source(
            name,
            start_date=config.start_date,
            end_date=config.end_date,
            max_days_per_run=config.max_days_per_run,
        )
        kwargs = {"refresh": config.refresh} if config.refresh else {}
        try:
            results = list(dlt.run(context=context, dlt_source=source, dlt_pipeline=pipeline, **kwargs))
        except Exception as exc:
            if is_lock_error(exc):
                raise RetryRequested(max_retries=5, seconds_to_wait=10) from exc
            raise
        for result in results:
            extra = load_metadata(pipeline, source.name, result.asset_key.path[-1], bounded=bool(config.end_date))
            yield MaterializeResult(asset_key=result.asset_key, metadata={**(result.metadata or {}), **extra})

    return _ingest


DLT_ASSETS = [make_dlt_assets(spec.name) for spec in SOURCES]


class LayerTranslator(DagsterDbtTranslator):
    """dbt nodes keyed `<schema>/<name>` and grouped by schema (layer)."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return super().get_asset_key(dbt_resource_props)
        return AssetKey([dbt_resource_props["schema"], dbt_resource_props["name"]])

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        return dbt_resource_props.get("schema")


def missing_raw_tables() -> dict[str, tuple[str, str]]:
    """dbt sources in `raw` with no table in the warehouse yet: {table: (source_name, table)}."""
    manifest = json.loads(dbt_project.manifest_path.read_text(encoding="utf-8"))
    sources = {
        s["name"]: (s["source_name"], s["name"]) for s in manifest["sources"].values() if s["schema"] == DATASET_NAME
    }
    path = warehouse_path()
    if not path.exists():
        return sources
    con = duckdb.connect(str(path), read_only=True)
    try:
        existing = {r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = ?", [DATASET_NAME]
        ).fetchall()}
    finally:
        con.close()
    return {name: ref for name, ref in sources.items() if name not in existing}


class TransformConfig(Config):
    scope: str = "recent"  # recent: tests see rows from pending loads only; all: whole warehouse
    full_refresh: bool = False
    command: str = "build"  # build: models + tests; test: tests only, no failure skips another test
    docs: bool = False  # refresh the dbt docs catalogue afterwards


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=LayerTranslator(),
    pool=WAREHOUSE_POOL,
)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource, config: TransformConfig) -> Iterator[Any]:
    missing = missing_raw_tables()
    if "_dlt_loads" in missing:
        context.log.info("No dlt load has completed yet; nothing to transform.")
        return
    load_ids = pending_load_ids()
    context.log.info(f"dlt loads pending for dbt: {load_ids}")
    args = dbt_build_args(
        load_ids,
        orchestrator_run_id=context.run_id,
        scope=config.scope,
        full_refresh=config.full_refresh,
        command=config.command,
    )
    if missing:
        context.log.warning(f"Skipping models downstream of unloaded raw tables: {sorted(missing)}")
        args += ["--exclude", " ".join(f"source:{source}.{table}+" for source, table in sorted(missing.values()))]
    invocation = dbt.cli(args, context=context, raise_on_error=False)
    yield from invocation.stream()
    if config.docs:
        run_dbt(["docs", "generate", "--quiet"])
    if not invocation.is_successful():
        error = invocation.get_error()
        if is_lock_error(error):
            raise RetryRequested(max_retries=5, seconds_to_wait=10) from error
        if error:
            raise error
