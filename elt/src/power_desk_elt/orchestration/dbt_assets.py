"""One Dagster asset per dbt node (`<schema>/<model>`), built in one dbt invocation.

The invocation processes the pending dlt loads. Models read never-loaded raw tables as empty
(`dlt_source`); tests downstream of them are skipped until their first load. dbt stamps the Dagster run id
into its artifacts and log lines. dbt reads the
warehouse location from the environment (`elt/dbt/profiles.yml`) and dagster-dbt finds `dbt` on
PATH; `power-desk-dagster` sets both for the whole Dagster process.
"""

from collections.abc import Iterator, Mapping
import os
from typing import Any, Literal

from dagster import AssetExecutionContext, AssetKey, Config
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from power_desk_elt.orchestration.warehouse_lock import WAREHOUSE_POOL, retry_run_if_locked
from power_desk_elt.settings import DBT_PROJECT_DIR
from power_desk_elt.transform.dbt import DAGSTER_RUN_ID_ENV, DbtRun, run_dbt, tests_downstream_of, unloaded_raw_tables
from power_desk_elt.transform.loads import pending_load_ids

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()
# a fresh checkout has no manifest yet: the assets below are defined from it (tests, `dg list defs`)
if not dbt_project.manifest_path.exists() and run_dbt(["parse"]) != 0:
    raise RuntimeError(f"`dbt parse` failed; the dbt assets need {dbt_project.manifest_path}")


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


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=LayerTranslator(),
    pool=WAREHOUSE_POOL,
)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource, config: TransformConfig) -> Iterator[Any]:
    unloaded = unloaded_raw_tables(dbt_project.manifest_path)
    if ("dlt", "_dlt_loads") in unloaded:
        context.log.info("No dlt load has completed yet; nothing to transform.")
        return
    dbt_run = DbtRun(command=config.command, scope=config.scope, full_refresh=config.full_refresh)
    args = dbt_run.args(pending_load_ids(), context.run.run_id)
    if unloaded:
        context.log.warning(f"Skipping tests downstream of unloaded raw tables: {[table for _, table in unloaded]}")
        args += ["--exclude", tests_downstream_of(unloaded)]
    os.environ[DAGSTER_RUN_ID_ENV] = context.run.run_id  # read by the dbt process; the run has its own process
    invocation = dbt.cli(args, context=context, raise_on_error=False)
    yield from invocation.stream()
    if config.docs:
        run_dbt(["docs", "generate", "--quiet"])
    if not invocation.is_successful():
        error = invocation.get_error()
        retry_run_if_locked(error)
        if error:
            raise error
