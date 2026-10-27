"""Read-only queries over the warehouse; unqualified names resolve against marts, ods, dims and raw."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import time
from typing import Any

from power_desk import warehouse
from power_desk.settings import warehouse_path

SEARCH_PATH = "marts,ods,dims,raw,main"
GB_DATASETS = ("FUELINST", "PVLIVE")
DATE_PLACEHOLDERS = ("start_date", "end_date")


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
    """Date range, fuel types and settlement periods of the GB marts."""
    options: dict[str, Any] = {
        "min_date": None,
        "max_date": None,
        "day_count": 0,
        "fuel_types": [],
        "settlement_periods": list(range(1, 51)),
        "table_counts": {},
    }
    if not Path(db_path or warehouse_path()).exists():
        return options
    with warehouse.connect(db_path) as con:
        if "mart_gb_generation_mix" not in warehouse.table_names(con, "marts"):
            return options
        options["min_date"], options["max_date"], options["day_count"] = con.execute(
            "select min(settlement_date)::text, max(settlement_date)::text, count(distinct settlement_date) "
            "from marts.mart_gb_generation_mix"
        ).fetchone()
        options["fuel_types"] = [
            code
            for (code,) in con.execute(
                "select distinct source_code from ods.ods_generation_actual where source_dataset in (?, ?) order by 1",
                list(GB_DATASETS),
            ).fetchall()
        ]
        options["table_counts"] = {
            table: con.execute(f"select count(*) from {schema}.{table}").fetchone()[0]
            for schema, table in [
                ("raw", "bmrs__fuelinst"),
                ("raw", "bmrs__indo"),
                ("ods", "ods_generation_actual"),
                ("marts", "mart_gb_generation_mix"),
            ]
        }
    return options
