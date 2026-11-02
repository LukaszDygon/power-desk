"""Shared fixtures: the widget registry and the warehouse stay out of the repo."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    registry = tmp_path / "widgets.json"
    monkeypatch.setenv("POWER_DESK_DUCKDB_PATH", str(tmp_path / "unused.duckdb"))
    monkeypatch.setattr("power_desk_dashboard.widgets.REGISTRY", registry)
    return registry
