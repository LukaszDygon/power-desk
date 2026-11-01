from __future__ import annotations

from pathlib import Path

import pytest

from power_desk_services.landing import Landing


@pytest.fixture
def landing_root(tmp_path: Path) -> Path:
    return tmp_path / "landing"


@pytest.fixture
def landing(tmp_path: Path, landing_root: Path, monkeypatch: pytest.MonkeyPatch) -> Landing:
    monkeypatch.setenv("POWER_DESK_SERVICES_PIPELINES_DIR", str(tmp_path / "pipelines"))
    return Landing("test_source", url=landing_root.as_posix())
