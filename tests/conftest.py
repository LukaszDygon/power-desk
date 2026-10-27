"""Shared fixtures: an isolated environment, and the seed week loaded through every pipeline and built by dbt."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import shutil

import pytest

from power_desk.ingest.seed.load import load_seed
from power_desk.ingest.seed.replay import SEED_START
from power_desk.transform.dbt import DbtRun


@pytest.fixture(scope="session", autouse=True)
def isolated_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """dlt state, schema exports, warehouses and the widget registry stay out of the repo."""
    root = tmp_path_factory.mktemp("env")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("POWER_DESK_START_DATE", SEED_START)
        mp.setenv("POWER_DESK_PIPELINES_DIR", str(root / "pipelines"))
        mp.setenv("POWER_DESK_EXPORT_SCHEMAS", "0")
        mp.setenv("POWER_DESK_DUCKDB_PATH", str(root / "unused.duckdb"))
        mp.setattr("power_desk.dashboard.widgets.REGISTRY", root / "widgets.json")
        yield root


@pytest.fixture(scope="session")
def seeded_warehouse(tmp_path_factory: pytest.TempPathFactory, isolated_env: Path) -> Path:
    root = tmp_path_factory.mktemp("warehouse")
    db = root / "warehouse.duckdb"
    load_seed(db)
    assert DbtRun().run_pending(db, target_path=root / "target") == 0
    pytest.MonkeyPatch().setenv("POWER_DESK_DBT_MANIFEST", str(root / "target" / "manifest.json"))
    return db


@pytest.fixture
def warehouse_copy(seeded_warehouse: Path, tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    shutil.copy(seeded_warehouse, path)
    return path
