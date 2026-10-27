"""Jobs, cron schedules, the catch-up sensor and cursor-lag checks, derived from `jobs.INGEST_JOBS`."""


from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetKey,
    AssetSelection,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    DagsterInstance,
    DagsterRunStatus,
    RunConfig,
    RunRequest,
    RunsFilter,
    ScheduleDefinition,
    ScheduleEvaluationContext,
    SensorEvaluationContext,
    SkipReason,
    asset_check,
    define_asset_job,
    sensor,
)

from power_desk.ingest.pipelines import DATASET_NAME, environment
from power_desk.orchestration.assets import TransformConfig, dbt_models
from power_desk.orchestration.jobs import INGEST_JOBS, NIGHTLY_CRON, IngestJob

# Automation only starts by itself in prod; in dev, turn schedules/sensors on in the UI when needed.
SCHEDULE_STATUS = DefaultScheduleStatus.RUNNING if environment() == "prod" else DefaultScheduleStatus.STOPPED
SENSOR_STATUS = DefaultSensorStatus.RUNNING if environment() == "prod" else DefaultSensorStatus.STOPPED

IN_FLIGHT = [
    DagsterRunStatus.QUEUED,
    DagsterRunStatus.NOT_STARTED,
    DagsterRunStatus.STARTING,
    DagsterRunStatus.STARTED,
]

# Ingest jobs run every dbt model: marts only process pending loads, so untouched ones are
# cheap no-ops, and marts combining tables from several jobs refresh on any of their schedules.
ALL_DBT = AssetSelection.assets(dbt_models)


def table_keys(job: IngestJob) -> list[AssetKey]:
    return [AssetKey([DATASET_NAME, table]) for table in job.tables]


ingest_jobs = {
    job.name: define_asset_job(
        job.name,
        selection=AssetSelection.assets(*table_keys(job)) | ALL_DBT,
        description=f"{job.description} dlt: {', '.join(job.tables)}; then dbt build scoped to pending loads.",
    )
    for job in INGEST_JOBS
}
dbt_nightly = define_asset_job(
    "dbt_nightly",
    selection=ALL_DBT,
    config=RunConfig(ops={"dbt_models": TransformConfig(scope="all", command="test", docs=True)}),
    description="Unscoped dbt tests over the whole warehouse (completeness from the start date) + dbt docs.",
)
backfill = define_asset_job(
    "backfill",
    selection=AssetSelection.all(),
    description=(
        "Configurable ingest + dbt. Set ops.<source>_ingest.config.{start_date,end_date,refresh}; "
        "use ops.dbt_models.config.scope=all to test the full range."
    ),
)

JOBS = [*ingest_jobs.values(), dbt_nightly, backfill]


def job_in_flight(instance: DagsterInstance, job_name: str) -> bool:
    return bool(instance.get_runs(filters=RunsFilter(job_name=job_name, statuses=IN_FLIGHT), limit=1))


def make_schedule(name: str, job_name: str, cron: str) -> ScheduleDefinition:
    def evaluate(context: ScheduleEvaluationContext) -> RunRequest | SkipReason:
        if job_in_flight(context.instance, job_name):
            return SkipReason(f"{job_name} is still running; skipping this tick")
        return RunRequest()

    return ScheduleDefinition(
        name=name,
        cron_schedule=cron,
        job_name=job_name,
        execution_timezone="UTC",
        execution_fn=evaluate,
        default_status=SCHEDULE_STATUS,
    )


SCHEDULES = [make_schedule(job.schedule, job.name, job.cron) for job in INGEST_JOBS] + [
    make_schedule("nightly", dbt_nightly.name, NIGHTLY_CRON)
]


def latest_metadata(instance: DagsterInstance, key: AssetKey) -> dict[str, object]:
    event = instance.get_latest_materialization_event(key)
    if not event or not event.asset_materialization:
        return {}
    return {k: v.value for k, v in event.asset_materialization.metadata.items()}


@sensor(jobs=list(ingest_jobs.values()), minimum_interval_seconds=120, default_status=SENSOR_STATUS)
def catchup_sensor(context: SensorEvaluationContext):
    """Re-run an ingest job straight away while its last run stopped at `max_days_per_run`.

    The run key includes the cursor, so a cursor that stops advancing never loops.
    """
    for job in INGEST_JOBS:
        if job_in_flight(context.instance, job.name):
            continue
        for key in table_keys(job):
            meta = latest_metadata(context.instance, key)
            if meta.get("window_capped"):
                yield RunRequest(
                    run_key=f"{job.name}:{key.to_user_string()}:{meta.get('cursor_last_value')}",
                    job_name=job.name,
                    tags={"power_desk/trigger": "catchup", "power_desk/cursor": str(meta.get("cursor_last_value"))},
                )
                break


def make_cursor_lag_check(key: AssetKey, threshold: int):
    @asset_check(asset=key, name="cursor_lag", description=f"dlt cursor lags now by at most {threshold} min")
    def _check(context: AssetCheckExecutionContext) -> AssetCheckResult:
        meta = latest_metadata(context.instance, key)
        lag = meta.get("cursor_lag_minutes")
        return AssetCheckResult(
            passed=lag is not None and float(lag) <= threshold,
            severity=AssetCheckSeverity.WARN,
            metadata={"cursor_lag_minutes": float(lag) if lag is not None else -1.0, "threshold_minutes": threshold,
                      "cursor_last_value": str(meta.get("cursor_last_value", ""))},
        )

    return _check


CURSOR_LAG_CHECKS = [
    make_cursor_lag_check(key, job.max_cursor_lag_minutes)
    for job in INGEST_JOBS
    if job.max_cursor_lag_minutes is not None
    for key in table_keys(job)
]
SENSORS = [catchup_sensor]
