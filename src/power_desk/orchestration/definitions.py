"""Dagster code location for Power Desk (`uv run dg dev`)."""

from dagster import Definitions
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource

from power_desk.orchestration.assets import DLT_ASSETS, dbt_models, dbt_project
from power_desk.orchestration.automation import CURSOR_LAG_CHECKS, JOBS, SCHEDULES, SENSORS
from power_desk.transform import DBT_EXECUTABLE

defs = Definitions(
    assets=[*DLT_ASSETS, dbt_models],
    asset_checks=CURSOR_LAG_CHECKS,
    jobs=JOBS,
    schedules=SCHEDULES,
    sensors=SENSORS,
    resources={
        "dlt": DagsterDltResource(),
        "dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=str(DBT_EXECUTABLE)),
    },
)
