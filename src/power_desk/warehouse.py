"""DuckDB warehouse access shared by the dashboard, the orchestrator and the CLIs.

DuckDB allows one writer per file: readers retry while dlt or dbt hold the lock.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import time

import duckdb

from power_desk.settings import warehouse_path


def is_lock_error(error: BaseException | str | None) -> bool:
    text = str(error or "").lower()
    return "could not set lock" in text or "conflicting lock" in text


@contextmanager
def connect(
    path: Path | str | None = None, read_only: bool = True, timeout: float = 10.0
) -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection to the warehouse, retried while another process holds its lock."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            con = duckdb.connect(Path(path or warehouse_path()).as_posix(), read_only=read_only)
            break
        except (duckdb.IOException, duckdb.ConnectionException) as exc:
            if not is_lock_error(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(0.15)
    try:
        yield con
    finally:
        con.close()


def table_names(con: duckdb.DuckDBPyConnection, schema: str, base_tables_only: bool = False) -> set[str]:
    kind = " and table_type = 'BASE TABLE'" if base_tables_only else ""
    rows = con.execute(
        f"select table_name from information_schema.tables where table_schema = ?{kind}", [schema]
    ).fetchall()
    return {name for (name,) in rows}
