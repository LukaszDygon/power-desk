"""The seed week, loaded through every pipeline and built by dbt: the warehouse the dashboard reads.

The ELT builds it, as in production; the dashboard itself only reads the file and the dbt manifest.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from power_desk_elt.ingest.seed.load import load_seed
from power_desk_elt.ingest.seed.replay import SEED_START
from power_desk_elt.transform.dbt import DbtRun


@pytest.fixture(scope="session")
def seeded_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    root = tmp_path_factory.mktemp("warehouse")
    db = root / "warehouse.duckdb"
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("POWER_DESK_START_DATE", SEED_START)
        mp.setenv("POWER_DESK_PIPELINES_DIR", str(root / "pipelines"))
        mp.setenv("POWER_DESK_EXPORT_SCHEMAS", "0")
        load_seed(db)
        assert DbtRun().run_pending(db, target_path=root / "target") == 0
        mp.setenv("POWER_DESK_DBT_MANIFEST", str(root / "target" / "manifest.json"))
        yield db
