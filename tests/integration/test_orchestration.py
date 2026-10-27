"""Dagster jobs end to end against the replayed publishers: dlt, then dbt for the pending loads, and catch-up."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dagster import AssetKey, DagsterInstance, build_sensor_context
import pytest

from power_desk.ingest.seed.replay import SeedPublishers, replay
from power_desk.transform.dbt import run_dbt
from power_desk.transform.loads import tracked_models
from tests.support import query


@pytest.fixture(scope="module")
def defs():
    assert run_dbt(["parse", "--quiet"]) == 0  # dagster-dbt reads the manifest; make it match the project
    from power_desk.orchestration.definitions import defs

    return defs


@pytest.fixture
def live(tmp_path, monkeypatch):
    """Publishers serving the last two days, scheduled from yesterday, into a fresh warehouse."""
    today = datetime.now(UTC).date()
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(tmp_path / "warehouse.duckdb"))
    monkeypatch.setenv("POWER_DESK_START_DATE", (today - timedelta(days=1)).isoformat())
    with replay(SeedPublishers.from_seed(start_date=(today - timedelta(days=2)).isoformat(), num_days=2)):
        yield tmp_path / "warehouse.duckdb"


def test_ingest_jobs_load_then_transform_and_audit_every_load(defs, live):
    instance = DagsterInstance.ephemeral()
    actuals = defs.resolve_job_def("ingest_actuals").execute_in_process(instance=instance)
    assert actuals.success
    metadata = instance.get_latest_materialization_event(AssetKey(["raw", "bmrs__indo"])).asset_materialization.metadata
    assert metadata["dlt_load_ids"].value and metadata["window_capped"].value is False
    audit = query(live, "select load_id, model_name, orchestrator_run_id from dlt_meta.dlt_load_audit")
    assert {r[1] for r in audit} == set(tracked_models())
    assert {r[0] for r in audit} >= set(metadata["dlt_load_ids"].value) and {r[2] for r in audit} == {actuals.run_id}

    assert defs.resolve_job_def("ingest_forecasts").execute_in_process(instance=instance).success
    assert defs.resolve_job_def("ingest_actuals").execute_in_process(instance=instance).success
    assert query(live, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
    assert defs.resolve_job_def("dbt_nightly").execute_in_process(instance=instance).success


def test_catchup_sensor_reruns_a_capped_job_until_its_cursor_is_current(defs, live, monkeypatch):
    monkeypatch.setenv("POWER_DESK_START_DATE", (datetime.now(UTC).date() - timedelta(days=2)).isoformat())
    instance = DagsterInstance.ephemeral()
    capped = {
        "ops": {
            "bmrs_ingest": {"config": {"max_days_per_run": 0}},
            "pvlive_ingest": {"config": {"max_days_per_run": 0}},
        }
    }
    job = defs.resolve_job_def("ingest_actuals")
    assert job.execute_in_process(instance=instance, run_config=capped).success

    sensor = defs.get_sensor_def("catchup_sensor")
    assert [r.job_name for r in sensor(build_sensor_context(instance=instance, definitions=defs))] == ["ingest_actuals"]
    assert job.execute_in_process(instance=instance).success
    assert list(sensor(build_sensor_context(instance=instance, definitions=defs))) == []
