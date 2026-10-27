"""Helpers shared by integration tests."""

from __future__ import annotations

from pathlib import Path

from power_desk import warehouse
from power_desk.transform.dbt import dbt_args, run_dbt
from power_desk.transform.loads import pending_load_ids


def query(db: Path, sql: str) -> list[tuple]:
    with warehouse.connect(db) as con:
        return con.execute(sql).fetchall()


def build(db: Path, tmp_path: Path, scope: str = "recent") -> int:
    return run_dbt(
        dbt_args(pending_load_ids(db), orchestrator_run_id="test-run", scope=scope), db, target_path=tmp_path / "target"
    )
