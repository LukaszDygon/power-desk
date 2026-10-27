"""Dagster definitions, ingest -> dbt runs in-process against the fake API, and catch-up."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dagster import AssetKey, DagsterInstance, build_sensor_context
import duckdb
import pytest

from power_desk.ingest import common
from power_desk.transform import run_dbt
from tests.fake_api import FakeApi


@pytest.fixture(scope="module")
def defs():
    # dagster-dbt only re-parses under `dagster dev`; make sure the manifest matches the project.
    assert run_dbt(["parse", "--quiet"]) == 0
    from power_desk.orchestration.definitions import defs

    return defs


@pytest.fixture
def live_env(tmp_path, monkeypatch):
    """Fresh warehouse + fake API covering the last two days, scheduled from yesterday."""
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    api = FakeApi((datetime.now(UTC).date() - timedelta(days=2)).isoformat(), 2, tmp_path / "api")
    monkeypatch.setattr(common, "fetch_json", api.fetch_json)
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(tmp_path / "warehouse.duckdb"))
    monkeypatch.setenv("POWER_DESK_START_DATE", yesterday)
    return tmp_path / "warehouse.duckdb"


def test_definitions_load(defs):
    assert {j.name for j in defs.jobs} >= {"ingest_actuals", "ingest_forecasts", "dbt_nightly", "backfill"}
    crons = {s.name: (s.cron_schedule, s.execution_timezone) for s in defs.schedules}
    assert crons["actuals_halfhourly"] == ("5,35 * * * *", "UTC")
    graph = defs.resolve_asset_graph()
    # dbt sources resolve to the dlt assets: one lineage graph from API to marts
    assert AssetKey(["raw", "raw_fuelinst"]) in graph.get(AssetKey(["staging", "stg_bmrs__fuelinst"])).parent_keys
    # an entity unions its sources' staging models and resolves dimension keys via the mappings
    assert graph.get(AssetKey(["ods", "ods_generation_actual"])).parent_keys == {
        AssetKey(["staging", "stg_bmrs__fuelinst"]), AssetKey(["staging", "stg_pvlive__solar"]),
        AssetKey(["dims", "source_datasets"]), AssetKey(["dims", "map_technology"]), AssetKey(["dims", "map_border"]),
    }


def test_every_raw_table_is_scheduled_by_exactly_one_ingest_job():
    from power_desk.ingest.pipelines import SOURCES, make_source
    from power_desk.orchestration.jobs import INGEST_JOBS

    scheduled = [table for job in INGEST_JOBS for table in job.tables]
    assert len(scheduled) == len(set(scheduled)), "a table is in more than one ingest job"
    tables = {name for spec in SOURCES for name in make_source(spec.name).resources}
    assert set(scheduled) == tables


def test_ingest_actuals_runs_dlt_then_dbt_with_load_ids(defs, live_env):
    instance = DagsterInstance.ephemeral()
    result = defs.resolve_job_def("ingest_actuals").execute_in_process(instance=instance)
    assert result.success

    meta = instance.get_latest_materialization_event(AssetKey(["raw", "raw_indo"])).asset_materialization.metadata
    load_ids = meta["dlt_load_ids"].value
    assert load_ids and meta["window_capped"].value is False

    con = duckdb.connect(str(live_env), read_only=True)
    audit = con.execute("select load_id, model_name, orchestrator_run_id from dlt_meta.dlt_load_audit").fetchall()
    con.close()
    # forecasts never loaded yet: marts needing them are skipped and their loads stay pending
    assert {r[1] for r in audit} == {"mart_generation_mix"}
    assert {r[0] for r in audit} >= set(load_ids)
    assert {r[2] for r in audit} == {result.run_id}

    forecasts = defs.resolve_job_def("ingest_forecasts").execute_in_process(instance=instance)
    assert forecasts.success
    con = duckdb.connect(str(live_env), read_only=True)
    assert con.execute("select count(*) from dlt_meta.dlt_pending_loads").fetchone()[0] == 0
    assert con.execute("select count(*) from marts.mart_demand_vs_forecast where actual_demand_mw is not null "
                       "and forecast_demand_mw is not null").fetchone()[0] > 0
    con.close()

    # nothing new upstream: the next run still succeeds and leaves nothing pending
    assert defs.resolve_job_def("ingest_actuals").execute_in_process(instance=instance).success
    con = duckdb.connect(str(live_env), read_only=True)
    assert con.execute("select count(*) from dlt_meta.dlt_pending_loads").fetchone()[0] == 0
    con.close()

    # nightly: unscoped tests over everything since POWER_DESK_START_DATE (the fake API has no gaps)
    assert defs.resolve_job_def("dbt_nightly").execute_in_process(instance=instance).success


def test_catchup_sensor_requests_runs_until_cursor_is_current(defs, live_env, monkeypatch):
    monkeypatch.setenv("POWER_DESK_START_DATE", (datetime.now(UTC).date() - timedelta(days=2)).isoformat())
    instance = DagsterInstance.ephemeral()
    run_config = {"ops": {"bmrs_ingest": {"config": {"max_days_per_run": 0}},
                          "pvlive_ingest": {"config": {"max_days_per_run": 0}}}}
    job = defs.resolve_job_def("ingest_actuals")
    assert job.execute_in_process(instance=instance, run_config=run_config).success

    sensor = defs.get_sensor_def("catchup_sensor")
    requests = list(sensor(build_sensor_context(instance=instance, definitions=defs)))
    assert [r.job_name for r in requests] == ["ingest_actuals"]

    # follow-up run without a cap reaches today: no further catch-up
    assert job.execute_in_process(instance=instance).success
    assert list(sensor(build_sensor_context(instance=instance, definitions=defs))) == []
