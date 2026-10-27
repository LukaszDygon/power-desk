"""Catch-up: re-run an ingest job straight away while its last run stopped at `max_days_per_run`.

The run key includes the cursor, so a cursor that stops advancing never loops.
"""

from dagster import DefaultSensorStatus, RunRequest, SensorEvaluationContext, sensor

from power_desk.orchestration.jobs import INGEST_JOBS, ingest_jobs
from power_desk.orchestration.runs import job_in_flight, latest_metadata
from power_desk.settings import environment

STATUS = DefaultSensorStatus.RUNNING if environment() == "prod" else DefaultSensorStatus.STOPPED


@sensor(jobs=list(ingest_jobs.values()), minimum_interval_seconds=120, default_status=STATUS)
def catchup_sensor(context: SensorEvaluationContext):
    for job in INGEST_JOBS:
        if job_in_flight(context.instance, job.name):
            continue
        capped = next(
            (m for key in job.asset_keys if (m := latest_metadata(context.instance, key)).get("window_capped")), None
        )
        if capped:
            cursor = str(capped.get("cursor_last_value"))
            yield RunRequest(
                run_key=f"{job.name}:{cursor}",
                job_name=job.name,
                tags={"power_desk/trigger": "catchup", "power_desk/cursor": cursor},
            )


SENSORS = [catchup_sensor]
