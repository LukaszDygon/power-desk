"""What the instance knows about runs and materializations, for schedules, sensors and checks."""

from typing import Any

from dagster import AssetKey, DagsterInstance, DagsterRunStatus, RunsFilter

IN_FLIGHT = [DagsterRunStatus.QUEUED, DagsterRunStatus.NOT_STARTED, DagsterRunStatus.STARTING, DagsterRunStatus.STARTED]


def job_in_flight(instance: DagsterInstance, job_name: str) -> bool:
    return bool(instance.get_runs(filters=RunsFilter(job_name=job_name, statuses=IN_FLIGHT), limit=1))


def latest_metadata(instance: DagsterInstance, key: AssetKey) -> dict[str, Any]:
    """The raw metadata values of the asset's latest materialization."""
    event = instance.get_latest_materialization_event(key)
    if not event or not event.asset_materialization:
        return {}
    return {name: value.value for name, value in event.asset_materialization.metadata.items()}
