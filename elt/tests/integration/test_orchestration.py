"""Dagster jobs end to end against the replayed publishers: dlt, then dbt for the pending loads, catch-up and
backfill."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dagster import AssetKey, DagsterInstance, build_sensor_context
import pytest

from power_desk_elt.ingest.seed.load import load_seed
from power_desk_elt.ingest.seed.replay import SEED_START, SeedPublishers, replay
from power_desk_elt.orchestration.jobs import INGEST_JOBS
from power_desk_elt.orchestration.runs import latest_metadata
from power_desk_elt.transform.dbt import run_dbt
from tests.support import query


@pytest.fixture(scope="module")
def defs():
    assert run_dbt(["parse", "--quiet"]) == 0  # dagster-dbt reads the manifest; make it match the project
    from power_desk_elt.orchestration.definitions import defs

    return defs


@pytest.fixture
def live(tmp_path, monkeypatch):
    """Publishers serving the last two days, scheduled from yesterday, into a warehouse holding only the EIC
    reference (as a deployment's first reference refresh leaves it)."""
    today = datetime.now(UTC).date()
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(tmp_path / "warehouse.duckdb"))
    load_seed(tmp_path / "warehouse.duckdb", sources=["entsoe_eic"])
    monkeypatch.setenv("POWER_DESK_START_DATE", (today - timedelta(days=1)).isoformat())
    with replay(SeedPublishers.from_seed(start_date=(today - timedelta(days=2)).isoformat(), num_days=2)):
        yield tmp_path / "warehouse.duckdb"


def test_ingest_jobs_load_then_transform_and_audit_every_load(defs, live):
    instance = DagsterInstance.ephemeral()
    actuals = defs.resolve_job_def("ingest_actuals").execute_in_process(instance=instance)
    assert actuals.success
    metadata = latest_metadata(instance, AssetKey(["raw", "bmrs__indo"]))
    assert metadata["dlt_load_ids"] and metadata["window_capped"] is False
    checks = {
        (e.asset_key, e.check_name): e
        for e in actuals.get_asset_check_evaluations()
        if e.check_name.startswith("recent")
    }
    for key in INGEST_JOBS[0].asset_keys:
        assert checks[key, "recently_fetched"].passed  # loaded just now
        assert checks[key, "recent_data"].metadata["newest"].value  # judged by the cursor, whatever its age
    assert query(live, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]

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


def test_a_backfill_partition_loads_its_month_then_dbt_processes_it(defs, warehouse_copy, monkeypatch):
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(warehouse_copy))
    with replay(SeedPublishers.from_seed()):
        job = defs.resolve_job_def("backfill_pvlive")
        assert job.execute_in_process(instance=DagsterInstance.ephemeral(), partition_key=SEED_START).success
    assert query(warehouse_copy, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
