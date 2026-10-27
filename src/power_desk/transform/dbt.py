"""dbt invocations shared by Dagster and the CLIs.

The orchestrator hands dbt the pending dlt load ids (`--vars dlt_load_ids`), the test scope
(`recent`: rows of pending loads only; `all`: the whole warehouse) and its run id.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from power_desk.settings import DBT_PROJECT_DIR, REPO_ROOT, backfill_start_date, environment, warehouse_path
from power_desk.transform.loads import pending_load_ids

DBT_EXECUTABLE = Path(sys.executable).with_name("dbt")


@dataclass(frozen=True)
class DbtRun:
    """A dbt invocation over the pending dlt loads.

    `command`: `build` (models and tests) or `test` (tests only). `scope`: `recent` tests the rows of
    pending loads only, `all` the whole warehouse. `full_refresh` rebuilds incremental models (`build` only).
    """

    command: Literal["build", "test"] = "build"
    scope: Literal["recent", "all"] = "recent"
    full_refresh: bool = False

    def args(self, load_ids: list[str], orchestrator_run_id: str | None = None) -> list[str]:
        variables = {
            "dlt_load_ids": load_ids,
            "dlt_scope": self.scope,
            **({"orchestrator_run_id": orchestrator_run_id} if orchestrator_run_id else {}),
        }
        return [
            self.command,
            "--vars",
            json.dumps(variables),
            *(["--full-refresh"] if self.full_refresh and self.command == "build" else []),
        ]

    def run_pending(
        self,
        db_path: Path | str | None = None,
        target_path: Path | str | None = None,
        orchestrator_run_id: str | None = None,
    ) -> int:
        """Run over the loads pending in the warehouse at `db_path`; returns dbt's exit code."""
        return run_dbt(self.args(pending_load_ids(db_path), orchestrator_run_id), db_path, target_path)


def dbt_env(db_path: Path | str | None = None) -> dict[str, str]:
    """dbt's environment: target (`POWER_DESK_ENV`), absolute warehouse path and start date."""
    return {
        **os.environ,
        "POWER_DESK_ENV": environment(),
        "POWER_DESK_DUCKDB_PATH": str(Path(db_path or warehouse_path()).resolve()),
        "POWER_DESK_START_DATE": backfill_start_date(),
    }


def run_dbt(args: list[str], db_path: Path | str | None = None, target_path: Path | str | None = None) -> int:
    command = [
        str(DBT_EXECUTABLE),
        *args,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(DBT_PROJECT_DIR),
        *(["--target-path", str(target_path)] if target_path else []),
    ]
    return subprocess.run(command, env=dbt_env(db_path), cwd=REPO_ROOT).returncode
