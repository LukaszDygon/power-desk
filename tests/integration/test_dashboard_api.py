"""Dashboard endpoints over the seeded warehouse."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from power_desk.dashboard.app import app


@pytest.fixture
def client(seeded_warehouse, monkeypatch):
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(seeded_warehouse))
    return TestClient(app)


def test_page_and_filters_describe_the_loaded_week(client):
    assert client.get("/").status_code == 200
    filters = client.get("/api/filters").json()
    assert (filters["min_date"], filters["max_date"]) == ("2024-03-01", "2024-03-07")
    assert {"WIND", "CCGT", "SOLAR"} <= set(filters["fuel_types"])


def test_query_binds_dates_and_can_only_read_the_warehouse(client, tmp_path):
    sql = "select count(*) from mart_gb_hourly_summary where date_utc between $start_date and $end_date"
    result = client.post("/api/query", json={"sql": sql, "start_date": "2024-03-01", "end_date": "2024-03-07"}).json()
    assert result["rows"] == [[168]]
    assert client.post("/api/query", json={"sql": sql, "start_date": "x' or 1=1 --"}).status_code == 422
    assert client.post("/api/query", json={"sql": "drop table raw.bmrs__fuelinst"}).status_code == 400
    escape = f"select 1; copy (select 1) to '{tmp_path / 'out.csv'}'"
    assert client.post("/api/query", json={"sql": escape}).status_code == 400
    assert not (tmp_path / "out.csv").exists()


def test_lineage_runs_from_publisher_to_widget(client):
    edges = {(e["source"], e["target"]) for e in client.get("/api/lineage").json()["edges"]}
    assert {
        ("api_bmrs__fuelinst", "bmrs__fuelinst"),
        ("stg_bmrs__fuelinst", "ods_generation_actual"),
        ("ods_generation_actual", "mart_gb_generation_mix"),
        ("ods_generation_actual", "mart_generation_actual"),
        ("mart_gb_generation_mix", "widget_generation_mix_timeseries"),
    } <= edges


def test_widgets_can_be_added_and_removed(client):
    widget = {"id": "pytest_card", "title": "Pytest Card", "type": "line", "sql": "select 1 as num"}
    assert "pytest_card" in [w["id"] for w in client.post("/api/widgets", json=widget).json()["widgets"]]
    assert "pytest_card" not in [w["id"] for w in client.delete("/api/widgets/pytest_card").json()["widgets"]]
