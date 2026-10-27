"""Pytest fixtures: an isolated seeded + dbt-built warehouse per session, copied per mutating test."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

import power_desk.db as db_module
from power_desk.db import PowerDeskDB
from power_desk.ingest.seed import load_seed
from power_desk.transform import dbt_build_args, pending_load_ids, run_dbt

SEED_START = "2024-03-01"


@pytest.fixture(scope="session", autouse=True)
def isolated_env(tmp_path_factory: pytest.TempPathFactory):
    """Keep dlt state, exported schemas and dbt artifacts out of the repo."""
    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("env")
    mp.setenv("POWER_DESK_START_DATE", SEED_START)
    mp.setenv("POWER_DESK_PIPELINES_DIR", str(root / "pipelines"))
    mp.setenv("POWER_DESK_EXPORT_SCHEMAS", "0")
    mp.setenv("POWER_DESK_DUCKDB_PATH", str(root / "unused.duckdb"))
    yield root
    mp.undo()


@pytest.fixture(scope="session")
def seeded_warehouse(tmp_path_factory: pytest.TempPathFactory, isolated_env: Path) -> Path:
    """Seed data loaded through dlt and fully built + tested by dbt."""
    root = tmp_path_factory.mktemp("warehouse")
    db_path = root / "warehouse.duckdb"
    load_seed(db_path)
    target = root / "dbt_target"
    assert run_dbt(dbt_build_args(pending_load_ids(db_path)), db_path=db_path, target_path=target) == 0
    pytest.MonkeyPatch().setenv("POWER_DESK_DBT_MANIFEST", str(target / "manifest.json"))
    return db_path


@pytest.fixture
def warehouse_copy(seeded_warehouse: Path, tmp_path: Path) -> Path:
    """A private copy of the seeded warehouse for tests that load or mutate data."""
    path = tmp_path / "warehouse.duckdb"
    shutil.copy(seeded_warehouse, path)
    return path


@pytest.fixture
def dashboard_db(seeded_warehouse: Path):
    """Point the dashboard singleton at the seeded warehouse."""
    original = db_module._db_instance
    db_module._db_instance = PowerDeskDB(db_path=seeded_warehouse)
    yield db_module._db_instance
    db_module._db_instance = original
