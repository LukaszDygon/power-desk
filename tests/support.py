"""Helpers shared by integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from power_desk import warehouse
from power_desk.transform.dbt import DbtRun


def query(db: Path, sql: str) -> list[tuple]:
    with warehouse.connect(db) as con:
        return con.execute(sql).fetchall()


def build(db: Path, tmp_path: Path, scope: Literal["recent", "all"] = "recent") -> int:
    return DbtRun(scope=scope).run_pending(db, tmp_path / "target", orchestrator_run_id="test-run")
