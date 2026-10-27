"""Tests for the dlt sources: windowing, incremental cursor state, bounded backfills, PVLive."""

from __future__ import annotations

from datetime import date

import dlt
import duckdb
import pytest

from power_desk.ingest import common
from power_desk.ingest.bmrs import (
    BmrsResourceConfig,
    BmrsSourceBuilder,
    build_default_bmrs_source,
    get_default_builder,
)
from power_desk.ingest.common import plan_window
from power_desk.ingest.pipelines import make_pipeline, make_source, window_state
from tests.fake_api import FakeApi


@pytest.fixture
def fake_api(tmp_path, monkeypatch):
    api = FakeApi("2024-03-01", 3, tmp_path / "api")
    monkeypatch.setattr(common, "fetch_json", api.fetch_json)
    return api


def test_builder_resource_registration():
    builder = BmrsSourceBuilder()
    builder.add_resource(BmrsResourceConfig(name="custom_feed", endpoint="/datasets/CUSTOM", primary_key=["id"]))
    assert builder.configs["custom_feed"].endpoint == "/datasets/CUSTOM"
    assert builder.configs["custom_feed"].lag == 0


def test_default_source_has_merge_disposition():
    source = build_default_bmrs_source(initial_date="2024-01-01", end_date="2024-01-01")
    for name in ["raw_fuelinst", "raw_indo", "raw_itsdo", "raw_demand_forecast", "raw_windfor"]:
        assert source.resources[name].compute_table_schema()["write_disposition"] == "merge"


def test_natural_keys_configured():
    configs = get_default_builder().configs
    assert configs["raw_fuelinst"].primary_key == ["settlementDate", "settlementPeriod", "fuelType", "startTime"]
    assert configs["raw_indo"].primary_key == ["settlementDate", "settlementPeriod"]


@pytest.mark.parametrize(
    ("start", "end", "max_days", "fetched_until", "expected"),
    [
        # open-ended, capped by max_days_per_run -> orchestrator should run again
        ("2024-03-01", None, 7, None, (date(2024, 3, 1), date(2024, 3, 8), True)),
        # open-ended, reaches today
        ("2024-03-08T10:00:00Z", None, 7, None, (date(2024, 3, 8), date(2024, 3, 10), False)),
        # cursor stuck in a publication gap: the window still advances past the last fetched day
        ("2024-02-01T10:00:00Z", None, 2, "2024-02-20", (date(2024, 2, 20), date(2024, 2, 22), True)),
        # bounded: end_value is exclusive, never capped
        ("2024-01-01", "2024-03-01", 7, None, (date(2024, 1, 1), date(2024, 2, 29), False)),
    ],
)
def test_plan_window(start, end, max_days, fetched_until, expected):
    assert plan_window(start, end, max_days, fetched_until=fetched_until, today=date(2024, 3, 10)) == expected


def test_incremental_run_resumes_from_cursor_and_reports_window(fake_api, tmp_path):
    db = tmp_path / "w.duckdb"
    pipeline = make_pipeline("bmrs", db_path=db)
    pipeline.run(make_source("bmrs", start_date="2024-03-01", max_days_per_run=1, resources=["raw_indo"]))
    state = window_state(pipeline, "bmrs")["raw_indo"]
    # settlement dates are padded by a day: 2024-03-01 period 1 can publish on 02-29 (BST)
    assert (state["first_day"], state["last_day"], state["capped"]) == ("2024-02-29", "2024-03-01", True)
    first_cursor = state["cursor_last_value"]

    pipeline.run(make_source("bmrs", start_date="2024-03-01", max_days_per_run=1, resources=["raw_indo"]))
    state = window_state(pipeline, "bmrs")["raw_indo"]
    assert (state["first_day"], state["last_day"]) == ("2024-03-01", "2024-03-02")  # resumed at the cursor's day
    assert state["cursor_last_value"] > first_cursor

    con = duckdb.connect(str(db), read_only=True)
    keys = con.execute("select count(*), count(distinct (settlement_date, settlement_period)) from raw.raw_indo").fetchone()
    assert keys[0] == keys[1]  # merge on natural key, no duplicates from overlapping windows


def test_bounded_backfill_leaves_cursor_untouched(fake_api, tmp_path):
    pipeline = make_pipeline("bmrs", db_path=tmp_path / "w.duckdb")
    pipeline.run(make_source("bmrs", start_date="2024-03-02", max_days_per_run=1, resources=["raw_indo"]))
    cursor = window_state(pipeline, "bmrs")["raw_indo"]["cursor_last_value"]

    info = pipeline.run(make_source("bmrs", start_date="2024-03-01", end_date="2024-03-01", resources=["raw_indo"]))
    assert info.loads_ids
    assert window_state(pipeline, "bmrs")["raw_indo"]["cursor_last_value"] == cursor


def test_fetch_errors_fail_the_run_instead_of_skipping_windows(monkeypatch, tmp_path):
    def broken(url, params=None, timeout=30, **headers):
        raise ConnectionError("API down")

    monkeypatch.setattr(common, "fetch_json", broken)
    pipeline = make_pipeline("bmrs", db_path=tmp_path / "w.duckdb")
    with pytest.raises(Exception, match="API down"):
        pipeline.run(make_source("bmrs", start_date="2024-03-01", end_date="2024-03-02", resources=["raw_indo"]))
    assert window_state(pipeline, "bmrs") == {}


def test_pvlive_rows_are_stored_raw(fake_api, tmp_path):
    db = tmp_path / "w.duckdb"
    make_pipeline("pvlive", db_path=db).run(make_source("pvlive", start_date="2024-03-01", end_date="2024-03-01"))
    con = duckdb.connect(str(db), read_only=True)
    cols = [r[0] for r in con.execute(
        "select column_name from information_schema.columns where table_schema = 'raw' and table_name = 'raw_pvlive_solar' order by ordinal_position"
    ).fetchall()]
    assert cols[:3] == ["pes_id", "datetime_gmt", "generation_mw"]
    # settlement day 03-01 padded to 02-29..03-02; the fake API has data from 03-01 00:30
    assert con.execute("select count(*) from raw.raw_pvlive_solar").fetchone()[0] == 96


def test_incremental_pointer_advances_and_stores():
    """dlt incremental pointer advances to the latest value with lag=0 across runs."""
    run_count = 0

    @dlt.resource(name="test_pointer_resource", write_disposition="merge", primary_key=["id"])
    def test_resource(cursor=dlt.sources.incremental("publishTime", initial_value="2021-01-01T00:00:00Z", lag=0)):
        nonlocal run_count
        run_count += 1
        if run_count == 1:
            yield [{"id": 1, "publishTime": "2021-01-01T12:00:00Z"}, {"id": 2, "publishTime": "2021-01-02T12:00:00Z"}]
        else:
            assert cursor.start_value == "2021-01-02T12:00:00Z"
            yield [{"id": 3, "publishTime": "2021-01-03T12:00:00Z"}]

    @dlt.source(name="test_inc_source")
    def _source():
        return [test_resource]

    pipeline = dlt.pipeline(pipeline_name="test_inc_pipeline", destination=dlt.destinations.duckdb(duckdb.connect(":memory:")))
    pipeline.run(_source())
    pipeline.run(_source())
    state = pipeline.state["sources"]["test_inc_source"]["resources"]["test_pointer_resource"]["incremental"]["publishTime"]
    assert state["last_value"] == "2021-01-03T12:00:00Z"


def test_environment_selects_warehouse_and_dlt_state(monkeypatch):
    from power_desk.ingest.pipelines import REPO_ROOT, environment, pipelines_dir, warehouse_path

    monkeypatch.delenv("POWER_DESK_DUCKDB_PATH", raising=False)
    monkeypatch.delenv("POWER_DESK_PIPELINES_DIR", raising=False)
    monkeypatch.delenv("POWER_DESK_ENV", raising=False)
    assert environment() == "dev"
    assert warehouse_path() == REPO_ROOT / "data" / "warehouse_dev.duckdb"
    monkeypatch.setenv("POWER_DESK_ENV", "prod")
    assert warehouse_path() == REPO_ROOT / "data" / "warehouse_prod.duckdb"
    assert pipelines_dir() == REPO_ROOT / ".dlt" / "pipelines" / "prod"
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", "/tmp/explicit.duckdb")
    assert str(warehouse_path()) == "/tmp/explicit.duckdb"  # an explicit path always wins
    monkeypatch.setenv("POWER_DESK_ENV", "staging")
    with pytest.raises(ValueError, match="POWER_DESK_ENV"):
        environment()
