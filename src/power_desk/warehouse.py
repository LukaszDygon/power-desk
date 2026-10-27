"""DuckDB warehouse access shared by the dashboard, the orchestrator and the CLIs.

DuckDB allows one writer per file: readers and loads retry while dlt or dbt hold the lock.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import time

import duckdb

from power_desk.settings import warehouse_path


@dataclass(frozen=True)
class LockRetry:
    """How long to keep retrying while another process holds the warehouse lock."""

    timeout_seconds: float
    interval_seconds: float


CONNECT_RETRY = LockRetry(timeout_seconds=10.0, interval_seconds=0.15)


def is_lock_error(error: BaseException | str | None) -> bool:
    text = str(error or "").lower()
    return "could not set lock" in text or "conflicting lock" in text


def retry_while_locked[T](
    action: Callable[[], T], retry: LockRetry, before_retry: Callable[[], None] | None = None
) -> T:
    """`action()`, retried while it fails on the warehouse lock until `retry.timeout_seconds` have passed."""
    deadline = time.monotonic() + retry.timeout_seconds
    while True:
        try:
            return action()
        except Exception as exc:
            if not is_lock_error(exc) or time.monotonic() >= deadline:
                raise
        if before_retry:
            before_retry()
        time.sleep(retry.interval_seconds)


@contextmanager
def connect(
    path: Path | str | None = None, read_only: bool = True, retry: LockRetry = CONNECT_RETRY
) -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection to the warehouse, retried while another process holds its lock."""
    location = Path(path or warehouse_path()).as_posix()
    con = retry_while_locked(lambda: duckdb.connect(location, read_only=read_only), retry)
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
