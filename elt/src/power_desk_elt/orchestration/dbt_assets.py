"""One Dagster asset per dbt node (`<schema>/<model>`), built in one dbt invocation (`DbtRun`).

dbt processes the pending dlt loads and scopes its tests itself; the run's config passes `DbtRun`'s
arguments, dbt node selection included. dbt stamps the Dagster run id into its artifacts and log lines.
dbt reads the warehouse location from the environment (`elt/dbt/profiles.yml`) and dagster-dbt finds `dbt`
on PATH; `power-desk-dagster` sets both for the whole Dagster process.
"""

from collections.abc import Iterator, Mapping
import os
from typing import Any, Literal

from dagster import AssetExecutionContext, AssetKey, Config
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from power_desk_elt.orchestration.warehouse_lock import WAREHOUSE_POOL, retry_run_if_locked
from power_desk_elt.settings import DBT_PROJECT_DIR
from power_desk_elt.transform.dbt import DbtRun, run_dbt

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR, profiles_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()
# dbt stamps `DBT_ENV_CUSTOM_ENV_<NAME>` variables into its artifacts (`metadata.env`) and log lines
DAGSTER_RUN_ID_ENV = "DBT_ENV_CUSTOM_ENV_DAGSTER_RUN_ID"
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
    """A `DbtRun` (see there), plus the docs catalogue."""

    command: Literal["build", "test"] = "build"
    scope: Literal["recent", "all"] = "recent"
    full_refresh: bool = False
    select: list[str] = []  # dbt node selection, e.g. `source:entsoe+`
    exclude: list[str] = []
    docs: bool = False  # regenerate the dbt docs catalogue afterwards


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=LayerTranslator(),
    pool=WAREHOUSE_POOL,
)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource, config: TransformConfig) -> Iterator[Any]:
    dbt_run = DbtRun(config.command, config.scope, config.full_refresh, tuple(config.select), tuple(config.exclude))
    os.environ[DAGSTER_RUN_ID_ENV] = context.run.run_id  # read by the dbt process; the run has its own process
    invocation = dbt.cli(dbt_run.args(), context=context, raise_on_error=False)
    yield from invocation.stream()
    if config.docs:
        run_dbt(["docs", "generate", "--quiet"])
    if not invocation.is_successful():
        error = invocation.get_error()
        retry_run_if_locked(error)
        if error:
            raise error
