"""Read-only queries over the warehouse; widget SQL reads the marts and their dimensions (unqualified names).

Widget SQL may use the dashboard's shared filter as parameters: `$start_date` / `$end_date` (dates),
`$areas` (EIC codes of the selected bidding zones, in selection order; every bidding zone when none is
selected) and `$bucket` (an interval for time series, sized to the date range).

Connections are read-only and sandboxed by DuckDB (no file, network or extension access, settings
locked), so widget SQL can read the warehouse and nothing else.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import threading
import time
from typing import Any

import duckdb

import power_desk_warehouse as warehouse
from power_desk_warehouse.settings import warehouse_path

SEARCH_PATH = "marts,dims"
SANDBOX = {"enable_external_access": False, "lock_configuration": True}
DEFAULT_WINDOW_DAYS = 7
# (longest range in days, bucket): a few hundred points per series at most
BUCKETS = ((14, timedelta(hours=1)), (120, timedelta(hours=6)), (400, timedelta(days=1)))
WEEK = timedelta(weeks=1)
# One query at a time: concurrent queries over the mart views contend for CPU and memory, and the
# dashboard's cards took 49 s side by side against 10 s one after another.
QUERY_LOCK = threading.Lock()
BIDDING_ZONES_SQL = (
    "select area_eic_code, display_name, long_name from dims.dim_area "
    "where is_current and is_bidding_zone order by display_name"
)
COUNTED_TABLES = (("raw", "bmrs__fuelinst"),)  # the page header's warehouse size


def run_query(
    sql: str,
    start_date: date | None = None,
    end_date: date | None = None,
    areas: list[str] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Columns, JSON-ready rows and duration of a query; it may use the shared filter parameters."""
    candidates = {"start_date": start_date, "end_date": end_date, "bucket": time_bucket(start_date, end_date)}
    params: dict[str, Any] = {name: value for name, value in candidates.items() if f"${name}" in sql}
    with QUERY_LOCK, warehouse.connect(db_path, config=SANDBOX) as con:
        started = time.perf_counter()
        con.execute(f"SET search_path = '{SEARCH_PATH}'")
        if "$areas" in sql:
            params["areas"] = areas or [code for code, *_ in con.execute(BIDDING_ZONES_SQL).fetchall()]
        cursor = con.execute(sql, params)
        columns = [d[0] for d in cursor.description or []]
        rows = [[v.isoformat() if hasattr(v, "isoformat") else v for v in row] for row in cursor.fetchall()]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def time_bucket(start_date: date | None, end_date: date | None) -> timedelta:
    """Time-series bucket for a date range: hourly for two weeks, coarser for longer ranges."""
    if start_date is None or end_date is None:
        return BUCKETS[0][1]
    days = (end_date - start_date).days + 1
    return next((bucket for longest, bucket in BUCKETS if days <= longest), WEEK)


def filter_options(db_path: Path | None = None) -> dict[str, Any]:
    """Date range of actual demand (every area), the default window, bidding zones and row counts of key tables."""
    options: dict[str, Any] = {
        "min_date": None,
        "max_date": None,
        "default_start_date": None,
        "day_count": 0,
        "areas": [],
        "table_counts": {},
    }
    if not Path(db_path or warehouse_path()).exists():
        return options
    with warehouse.connect(db_path, config=SANDBOX) as con:
        if "mart_demand_actual" not in warehouse.table_names(con, "marts"):
            return options
        return {**options, **_date_range(con), "areas": _bidding_zones(con), "table_counts": _table_counts(con)}


def _date_range(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    min_date, max_date, day_count = _single_row(
        con,
        "select min(timestamp_utc)::date, max(timestamp_utc)::date, count(distinct timestamp_utc::date) "
        "from marts.mart_demand_actual",
    )
    if max_date is None:
        return {}
    default_start = max(min_date, max_date - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return {
        "min_date": min_date.isoformat(),
        "max_date": max_date.isoformat(),
        "default_start_date": default_start.isoformat(),
        "day_count": day_count,
    }


def _bidding_zones(con: duckdb.DuckDBPyConnection) -> list[dict[str, str]]:
    cursor = con.execute(BIDDING_ZONES_SQL)
    columns = [d[0] for d in cursor.description or []]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _table_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    return {table: _single_row(con, f"select count(*) from {schema}.{table}")[0] for schema, table in COUNTED_TABLES}


def _single_row(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[Any, ...]:
    """The one row of an aggregate query."""
    row = con.execute(sql).fetchone()
    if row is None:
        raise LookupError(f"no row from: {sql}")
    return row
