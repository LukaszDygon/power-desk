"""Pytest fixtures for isolated testing."""

from __future__ import annotations

from pathlib import Path
import pytest
import duckdb

from power_desk.db import PowerDeskDB, get_db
import power_desk.db as db_module


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path: Path):
    """Ensures each test run executes against a clean isolated test DuckDB warehouse."""
    test_db_path = tmp_path / "test_warehouse.duckdb"
    db_module.load_seed_with_dlt(test_db_path)
    test_db = PowerDeskDB(db_path=test_db_path)
    test_db.initialize_views()
    # Monkeypatch the singleton instance
    original = db_module._db_instance
    db_module._db_instance = test_db
    yield test_db
    db_module._db_instance = original
