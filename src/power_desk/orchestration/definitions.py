"""Dagster code location (`python -m power_desk.cli.dagster`)."""

from dagster import Definitions
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource

from power_desk.orchestration.checks import CHECKS
from power_desk.orchestration.dbt_assets import dbt_models, dbt_project
from power_desk.orchestration.dlt_assets import DLT_ASSETS
from power_desk.orchestration.jobs import JOBS
from power_desk.orchestration.schedules import SCHEDULES
from power_desk.orchestration.sensors import SENSORS
from power_desk.transform.dbt import DBT_EXECUTABLE

defs = Definitions(
    assets=[*DLT_ASSETS, dbt_models],
    asset_checks=CHECKS,
    jobs=JOBS,
    schedules=SCHEDULES,
    sensors=SENSORS,
    resources={
        "dlt": DagsterDltResource(),
        "dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=str(DBT_EXECUTABLE)),
    },
)
