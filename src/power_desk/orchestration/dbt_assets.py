"""One Dagster asset per dbt node (`<schema>/<model>`), built in one dbt invocation.

The invocation processes the pending dlt loads. Models read never-loaded raw tables as empty
(`dlt_source`); tests downstream of them are skipped until their first load. dbt reads the
warehouse location from the environment (`transform/profiles.yml`) and dagster-dbt finds `dbt` on
PATH; `power-desk-dagster` sets both for the whole Dagster process.
"""

from collections.abc import Iterator, Mapping
import json
from typing import Any, Literal

from dagster import AssetExecutionContext, AssetKey, Config
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from power_desk import warehouse
from power_desk.ingest.pipeline import DATASET_NAME
from power_desk.orchestration.warehouse_lock import WAREHOUSE_POOL, retry_run_if_locked
from power_desk.settings import DBT_PROJECT_DIR, warehouse_path
from power_desk.transform.dbt import DbtRun, run_dbt
from power_desk.transform.loads import pending_load_ids

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
    """A `DbtRun` (see there for `scope`, `full_refresh` and `command`), plus the docs catalogue."""

    scope: Literal["recent", "all"] = "recent"
    full_refresh: bool = False
    command: Literal["build", "test"] = "build"
    docs: bool = False  # regenerate the dbt docs catalogue afterwards

    def dbt_run(self) -> DbtRun:
        return DbtRun(command=self.command, scope=self.scope, full_refresh=self.full_refresh)


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


def tests_downstream_of(tables: list[tuple[str, str]]) -> str:
    """dbt selector for the tests downstream of (dbt source, table) pairs."""
    return " ".join(f"source:{source}.{table}+,resource_type:test" for source, table in tables)


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
    args = config.dbt_run().args(pending_load_ids(), context.run.run_id)
    if unloaded:
        context.log.warning(f"Skipping tests downstream of unloaded raw tables: {[table for _, table in unloaded]}")
        args += ["--exclude", tests_downstream_of(unloaded)]
    invocation = dbt.cli(args, context=context, raise_on_error=False)
    yield from invocation.stream()
    if config.docs:
        run_dbt(["docs", "generate", "--quiet"])
    if not invocation.is_successful():
        error = invocation.get_error()
        retry_run_if_locked(error)
        if error:
            raise error
