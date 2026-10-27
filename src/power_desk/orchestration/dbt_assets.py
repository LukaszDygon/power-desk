"""One Dagster asset per dbt node (`<schema>/<model>`), built in one dbt invocation.

The invocation processes the pending dlt loads. Models read never-loaded raw tables as empty
(`dlt_source`); tests downstream of them are skipped until their first load. dbt reads the
warehouse location from the environment (`transform/profiles.yml`) and dagster-dbt finds `dbt` on
PATH, so both are set on import.
"""

from collections.abc import Iterator, Mapping
import json
import os
from typing import Any

from dagster import AssetExecutionContext, AssetKey, Config, RetryRequested
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from power_desk import warehouse
from power_desk.ingest.pipeline import DATASET_NAME
from power_desk.orchestration.dlt_assets import WAREHOUSE_POOL
from power_desk.settings import DBT_PROJECT_DIR, warehouse_path
from power_desk.transform.dbt import DBT_EXECUTABLE, dbt_args, run_dbt
from power_desk.transform.loads import pending_load_ids

os.environ.setdefault("POWER_DESK_DUCKDB_PATH", str(warehouse_path()))
os.environ["PATH"] = os.pathsep.join(
    dict.fromkeys([str(DBT_EXECUTABLE.parent), *os.environ.get("PATH", "").split(os.pathsep)])
)

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()


class LayerTranslator(DagsterDbtTranslator):
    """dbt nodes keyed `<schema>/<name>` and grouped by schema (layer)."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return super().get_asset_key(dbt_resource_props)
        return AssetKey([dbt_resource_props["schema"], dbt_resource_props["name"]])

    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str | None:
        return dbt_resource_props.get("schema")


class TransformConfig(Config):
    scope: str = "recent"  # recent: tests read rows of pending loads only; all: the whole warehouse
    full_refresh: bool = False
    command: str = "build"  # build: models and tests; test: tests only
    docs: bool = False  # regenerate the dbt docs catalogue afterwards


def unloaded_raw_tables() -> list[tuple[str, str]]:
    """(dbt source, table) of every declared raw table without a warehouse table yet."""
    manifest = json.loads(dbt_project.manifest_path.read_text(encoding="utf-8"))
    declared = {
        s["name"]: (s["source_name"], s["name"]) for s in manifest["sources"].values() if s["schema"] == DATASET_NAME
    }
    if not warehouse_path().exists():
        return sorted(declared.values())
    with warehouse.connect() as con:
        loaded = warehouse.table_names(con, DATASET_NAME)
    return sorted(ref for name, ref in declared.items() if name not in loaded)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=LayerTranslator(),
    pool=WAREHOUSE_POOL,
)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource, config: TransformConfig) -> Iterator[Any]:
    unloaded = unloaded_raw_tables()
    if ("dlt", "_dlt_loads") in unloaded:
        context.log.info("No dlt load has completed yet; nothing to transform.")
        return
    args = dbt_args(pending_load_ids(), context.run.run_id, config.scope, config.full_refresh, config.command)
    if unloaded:
        context.log.warning(f"Skipping tests downstream of unloaded raw tables: {[table for _, table in unloaded]}")
        args += ["--exclude", " ".join(f"source:{source}.{table}+,resource_type:test" for source, table in unloaded)]
    invocation = dbt.cli(args, context=context, raise_on_error=False)
    yield from invocation.stream()
    if config.docs:
        run_dbt(["docs", "generate", "--quiet"])
    if not invocation.is_successful():
        error = invocation.get_error()
        if warehouse.is_lock_error(error):
            raise RetryRequested(max_retries=5, seconds_to_wait=10) from error
        if error:
            raise error
