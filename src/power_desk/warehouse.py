"""DuckDB warehouse access shared by the dashboard, the orchestrator and the CLIs.

DuckDB allows one writer per file: readers and loads retry while dlt or dbt hold the lock.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
from tenacity import Retrying, retry_if_exception, stop_after_delay, wait_fixed

from power_desk.settings import warehouse_path


def is_lock_error(error: BaseException | str | None) -> bool:
    text = str(error or "").lower()
    return "could not set lock" in text or "conflicting lock" in text


@contextmanager
def connect(
    path: Path | str | None = None, read_only: bool = True, config: dict[str, Any] | None = None
) -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection to the warehouse, retried for up to 10 s while another process holds its lock."""
    retry = Retrying(
        retry=retry_if_exception(is_lock_error), stop=stop_after_delay(10), wait=wait_fixed(0.15), reraise=True
    )
    con = retry(duckdb.connect, Path(path or warehouse_path()).as_posix(), read_only=read_only, config=config or {})
    try:
        yield con
    finally:
        con.close()


def table_names(con: duckdb.DuckDBPyConnection, schema: str) -> set[str]:
    """Tables and views of `schema`."""
    return _names(con, "select table_name from information_schema.tables where table_schema = ?", schema)


def base_table_names(con: duckdb.DuckDBPyConnection, schema: str) -> set[str]:
    """Tables of `schema`, without views."""
    return _names(
        con,
        "select table_name from information_schema.tables where table_schema = ? and table_type = 'BASE TABLE'",
        schema,
    )


def _names(con: duckdb.DuckDBPyConnection, sql: str, schema: str) -> set[str]:
    return {name for (name,) in con.execute(sql, [schema]).fetchall()}
