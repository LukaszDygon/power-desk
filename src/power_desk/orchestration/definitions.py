"""Dagster code location (`python -m power_desk.cli.dagster`); runs log in the log standard (`logs.py`)."""

from dagster import Definitions
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource

from power_desk.orchestration.checks import CHECKS
from power_desk.orchestration.dbt_assets import dbt_models, dbt_project
from power_desk.orchestration.dlt_assets import DLT_ASSETS
from power_desk.orchestration.jobs import JOBS, check_every_raw_table_scheduled_once
from power_desk.orchestration.logs import configure_run_logs
from power_desk.orchestration.schedules import SCHEDULES
from power_desk.orchestration.sensors import SENSORS
from power_desk.transform.dbt import DBT_EXECUTABLE

check_every_raw_table_scheduled_once()
configure_run_logs()

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
