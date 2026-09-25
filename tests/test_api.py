"""Tests for FastAPI endpoints, queries, and widget management."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from power_desk.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "POWER DESK" in response.text
    assert "GridStack" in response.text or "grid-stack" in response.text


def test_api_filters(client):
    response = client.get("/api/filters")
    assert response.status_code == 200
    data = response.json()
    assert "min_date" in data
    assert "max_date" in data
    assert "WIND" in data["fuel_types"]
    assert "CCGT" in data["fuel_types"]


def test_api_lineage(client):
    response = client.get("/api/lineage")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    node_ids = {n["id"] for n in data["nodes"]}
    assert "raw_fuelinst" in node_ids
    assert "ods_generation_actual" in node_ids
    assert "mart_generation_mix" in node_ids


def test_api_query_safe_select(client):
    payload = {
        "sql": "SELECT COUNT(*) as total FROM mart_hourly_summary WHERE date_utc >= '{start_date}' AND date_utc <= '{end_date}'",
        "start_date": "2024-03-01",
        "end_date": "2024-03-07",
    }
    response = client.post("/api/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert "rows" in data
    assert data["rows"][0][0] > 0
    assert data["duration_ms"] >= 0


def test_api_query_rejects_mutations(client):
    payload = {
        "sql": "DROP TABLE raw_fuelinst",
    }
    response = client.post("/api/query", json=payload)
    assert response.status_code == 400


def test_api_widget_lifecycle(client):
    widget = {
        "id": "pytest_card",
        "title": "Pytest Card",
        "type": "line",
        "sql": "SELECT 1 as num",
        "grid": {"x": 0, "y": 0, "w": 4, "h": 3},
        "description": "Test widget",
        "config": {},
    }
    # Save
    res_post = client.post("/api/widgets", json=widget)
    assert res_post.status_code == 200

    # Get
    res_get = client.get("/api/widgets")
    assert res_get.status_code == 200
    ids = [w["id"] for w in res_get.json()]
    assert "pytest_card" in ids

    # Delete
    res_del = client.delete("/api/widgets/pytest_card")
    assert res_del.status_code == 200
    ids_after = [w["id"] for w in res_del.json()["widgets"]]
    assert "pytest_card" not in ids_after
