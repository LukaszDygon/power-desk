"""Cron schedules for the ingest jobs and the nightly test run; they start themselves only in prod."""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleDefinition, ScheduleEvaluationContext, SkipReason

from power_desk.orchestration.jobs import INGEST_JOBS, NIGHTLY_CRON, dbt_nightly
from power_desk.orchestration.runs import job_in_flight
from power_desk.settings import environment

STATUS = DefaultScheduleStatus.RUNNING if environment() == "prod" else DefaultScheduleStatus.STOPPED


def schedule(name: str, job_name: str, cron: str) -> ScheduleDefinition:
    def evaluate(context: ScheduleEvaluationContext) -> RunRequest | SkipReason:
        if job_in_flight(context.instance, job_name):
            return SkipReason(f"{job_name} is still running")
        return RunRequest()

    return ScheduleDefinition(
        name=name,
        cron_schedule=cron,
        job_name=job_name,
        execution_timezone="UTC",
        execution_fn=evaluate,
        default_status=STATUS,
    )


SCHEDULES = [schedule(job.schedule, job.name, job.cron) for job in INGEST_JOBS] + [
    schedule("nightly", dbt_nightly.name, NIGHTLY_CRON)
]
