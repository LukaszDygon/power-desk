"""Shared fixtures: the warehouse stays out of the repo."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(tmp_path / "unused.duckdb"))
