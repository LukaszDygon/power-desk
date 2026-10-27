"""dbt invocation helpers shared by Dagster and the CLI scripts.

The orchestrator hands dbt an explicit list of dlt load ids: every completed load
that at least one tracked model has not processed yet (`dlt_meta.dlt_pending_loads`,
or all completed loads before the first dbt build).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import duckdb

from power_desk.ingest.pipelines import REPO_ROOT, backfill_start_date, environment, warehouse_path

DBT_PROJECT_DIR = REPO_ROOT / "transform"
DBT_EXECUTABLE = Path(sys.executable).with_name("dbt")


def tracked_models(manifest: Path = DBT_PROJECT_DIR / "target" / "manifest.json") -> list[str] | None:
    """Models with `meta.dlt_tracked` (the marts) from the dbt manifest; None if not parsed yet."""
    if not manifest.exists():
        return None
    nodes = json.loads(manifest.read_text(encoding="utf-8"))["nodes"].values()
    return sorted(
        n.get("alias") or n["name"]
        for n in nodes
        if n["resource_type"] == "model" and (n.get("config", {}).get("meta") or {}).get("dlt_tracked")
    )


def pending_load_ids(db_path: Path | str | None = None) -> list[str]:
    """Completed dlt loads still pending for at least one tracked dbt model.

    Reads tables only (`raw._dlt_loads`, `dlt_meta.dlt_load_audit`): view definitions embed
    the DuckDB catalog name and break when the warehouse file is renamed until dbt rebuilds them.
    """
    path = Path(db_path or warehouse_path())
    if not path.exists():
        return []
    con = duckdb.connect(path.as_posix(), read_only=True)
    try:
        tables = {
            f"{s}.{t}"
            for s, t in con.execute(
                "select table_schema, table_name from information_schema.tables where table_type = 'BASE TABLE'"
            ).fetchall()
        }
        if "raw._dlt_loads" not in tables:
            return []
        tracked = tracked_models()
        if "dlt_meta.dlt_load_audit" not in tables or not tracked:
            sql, params = "select load_id from raw._dlt_loads where status = 0 order by load_id", []
        else:
            sql = f"""
                select l.load_id from raw._dlt_loads l
                where l.status = 0
                  and (select count(distinct a.model_name) from dlt_meta.dlt_load_audit a
                       where a.load_id = l.load_id and a.model_name in ({", ".join("?" for _ in tracked)})) < ?
                order by l.load_id
            """
            params = [*tracked, len(tracked)]
        return [row[0] for row in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def dbt_vars(load_ids: list[str], orchestrator_run_id: str | None = None, scope: str = "recent") -> dict[str, object]:
    out: dict[str, object] = {"dlt_load_ids": load_ids, "dlt_scope": scope}
    if orchestrator_run_id:
        out["orchestrator_run_id"] = orchestrator_run_id
    return out


def dbt_build_args(
    load_ids: list[str],
    orchestrator_run_id: str | None = None,
    scope: str = "recent",
    full_refresh: bool = False,
    command: str = "build",
) -> list[str]:
    args = [command, "--vars", json.dumps(dbt_vars(load_ids, orchestrator_run_id, scope))]
    if full_refresh and command == "build":
        args.append("--full-refresh")
    return args


def dbt_env(db_path: Path | str | None = None) -> dict[str, str]:
    """Environment for dbt: active environment (dbt target), absolute warehouse path, start date."""
    return {
        **os.environ,
        "POWER_DESK_ENV": environment(),
        "POWER_DESK_DUCKDB_PATH": str(Path(db_path or warehouse_path()).resolve()),
        "POWER_DESK_START_DATE": backfill_start_date(),
    }


def run_dbt(args: list[str], db_path: Path | str | None = None, target_path: Path | str | None = None) -> int:
    """Run the dbt CLI against the project (used by scripts and tests; Dagster uses DbtCliResource)."""
    cmd = [str(DBT_EXECUTABLE), *args, "--project-dir", str(DBT_PROJECT_DIR), "--profiles-dir", str(DBT_PROJECT_DIR)]
    if target_path:
        cmd += ["--target-path", str(target_path)]
    return subprocess.run(cmd, env=dbt_env(db_path), cwd=REPO_ROOT).returncode
