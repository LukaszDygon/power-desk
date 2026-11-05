"""dbt invocations shared by Dagster and the CLIs.

dbt decides what a run processes (the pending dlt loads, `macros/dlt/loads.sql`) and how far its tests look
(`dlt_scope`: `recent`, the rows of pending loads; `all`, every row). Which nodes run is dbt's own selection
(`select`, `exclude`). dbt writes its log file as JSON lines, each with its invocation id (docs/logging.md).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from power_desk_elt.settings import DBT_PROJECT_DIR, REPO_ROOT, backfill_start_date, environment, warehouse_path

DBT_EXECUTABLE = Path(sys.executable).with_name("dbt")


@dataclass(frozen=True)
class DbtRun:
    """A dbt invocation over the pending dlt loads.

    `command`: `build` (models and tests) or `test` (tests only). `scope`: `recent` tests the rows of
    pending loads only, `all` every row. `full_refresh` rebuilds incremental models (`build` only).
    `select`, `exclude`: dbt node selection (default: every node).
    """

    command: Literal["build", "test"] = "build"
    scope: Literal["recent", "all"] = "recent"
    full_refresh: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    def args(self) -> list[str]:
        return [
            self.command,
            "--vars",
            json.dumps({"dlt_scope": self.scope}),
            *(["--full-refresh"] if self.full_refresh and self.command == "build" else []),
            *(["--select", *self.select] if self.select else []),
            *(["--exclude", *self.exclude] if self.exclude else []),
        ]

    def run(self, db_path: Path | str | None = None, target_path: Path | str | None = None) -> int:
        """Run against the warehouse at `db_path`; returns dbt's exit code."""
        return run_dbt(self.args(), db_path, target_path)


def dbt_env(db_path: Path | str | None = None) -> dict[str, str]:
    """dbt's environment: target (`POWER_DESK_ENV`), absolute warehouse path and start date."""
    return {
        **os.environ,
        "POWER_DESK_ENV": environment(),
        "POWER_DESK_DUCKDB_PATH": str(Path(db_path or warehouse_path()).resolve()),
        "POWER_DESK_START_DATE": backfill_start_date(),
        "DBT_LOG_FORMAT_FILE": "json",
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
