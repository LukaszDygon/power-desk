"""Read-only queries over the warehouse; unqualified names resolve against marts, ods, dims and raw."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import time
from typing import Any

import duckdb

from power_desk import warehouse
from power_desk.settings import warehouse_path

SEARCH_PATH = "marts,ods,dims,raw,main"
GB_DATASETS = ("FUELINST", "PVLIVE")
DATE_PLACEHOLDERS = ("start_date", "end_date")
MAX_SETTLEMENT_PERIODS = 50  # the autumn clock-change day
COUNTED_TABLES = (
    ("raw", "bmrs__fuelinst"),
    ("raw", "bmrs__indo"),
    ("ods", "ods_generation_actual"),
    ("marts", "mart_gb_generation_mix"),
)


def bind_dates(sql: str, **dates: str | None) -> str:
    """Replace `{start_date}` / `{end_date}` with ISO dates (anything else is rejected)."""
    for name in DATE_PLACEHOLDERS:
        if value := dates.get(name):
            sql = sql.replace("{" + name + "}", date.fromisoformat(value).isoformat())
    return sql


def run_query(sql: str, params: list[Any] | None = None, db_path: Path | None = None) -> dict[str, Any]:
    """Columns, JSON-ready rows and duration of a read-only SELECT / WITH query."""
    if not sql.strip().upper().startswith(("SELECT", "WITH")):
        raise ValueError("only SELECT or WITH queries are allowed")
    started = time.perf_counter()
    with warehouse.connect(db_path) as con:
        con.execute(f"SET search_path = '{SEARCH_PATH}'")
        cursor = con.execute(sql, params or [])
        columns = [d[0] for d in cursor.description or []]
        rows = [[v.isoformat() if hasattr(v, "isoformat") else v for v in row] for row in cursor.fetchall()]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def filter_options(db_path: Path | None = None) -> dict[str, Any]:
    """Date range, fuel types and settlement periods of the GB marts, plus row counts of key tables."""
    options: dict[str, Any] = {
        "min_date": None,
        "max_date": None,
        "day_count": 0,
        "fuel_types": [],
        "settlement_periods": list(range(1, MAX_SETTLEMENT_PERIODS + 1)),
        "table_counts": {},
    }
    if not Path(db_path or warehouse_path()).exists():
        return options
    with warehouse.connect(db_path) as con:
        if "mart_gb_generation_mix" not in warehouse.table_names(con, "marts"):
            return options
        return {**options, **_date_range(con), "fuel_types": _fuel_types(con), "table_counts": _table_counts(con)}


def _date_range(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    min_date, max_date, day_count = _single_row(
        con,
        "select min(settlement_date)::text, max(settlement_date)::text, count(distinct settlement_date) "
        "from marts.mart_gb_generation_mix",
    )
    return {"min_date": min_date, "max_date": max_date, "day_count": day_count}


def _fuel_types(con: duckdb.DuckDBPyConnection) -> list[str]:
    placeholders = ", ".join("?" for _ in GB_DATASETS)
    rows = con.execute(
        f"select distinct source_code from ods.ods_generation_actual where source_dataset in ({placeholders}) "
        "order by 1",
        list(GB_DATASETS),
    ).fetchall()
    return [code for (code,) in rows]


def _table_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    return {table: _single_row(con, f"select count(*) from {schema}.{table}")[0] for schema, table in COUNTED_TABLES}


def _single_row(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[Any, ...]:
    """The one row of an aggregate query."""
    row = con.execute(sql).fetchone()
    if row is None:
        raise LookupError(f"no row from: {sql}")
    return row
