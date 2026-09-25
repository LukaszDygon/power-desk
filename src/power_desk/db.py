"""DuckDB Database Manager for Power Desk.

Manages connections, automated loading of seed/parquet tables, execution of
DBT-style ODS & Marts SQL views, and read-only parameterized query execution.
"""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any
import json

import duckdb

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "warehouse.duckdb"
SEED_DIR = REPO_ROOT / "data" / "seed"
MODELS_DIR = Path(__file__).resolve().parent / "models"


class PowerDeskDB:
    """Encapsulates the DuckDB analytical engine and SQL view layer."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con: duckdb.DuckDBPyConnection | None = None
        self.initialize()

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Returns or establishes a connection to the warehouse."""
        if self._con is None:
            self._con = duckdb.connect(database=self.db_path.as_posix(), read_only=False)
        return self._con

    def initialize(self) -> None:
        """Initializes raw tables from seed parquet if not present, and registers all views."""
        con = self.get_connection()

        # Check if raw_fuelinst exists
        tables = con.execute("SHOW TABLES").fetchall()
        existing_tables = {t[0] for t in tables}

        raw_tables = ["raw_fuelinst", "raw_indo", "raw_demand_forecast", "raw_windfor"]
        for tbl in raw_tables:
            if tbl not in existing_tables:
                parquet_path = SEED_DIR / f"{tbl}.parquet"
                if parquet_path.exists():
                    con.execute(f"CREATE TABLE {tbl} AS SELECT * FROM read_parquet('{parquet_path.as_posix()}')")
                    logger.info("Loaded seed table %s from %s", tbl, parquet_path.name)

        # Apply ODS Views
        ods_dir = MODELS_DIR / "ods"
        if ods_dir.exists():
            for sql_file in sorted(ods_dir.glob("*.sql")):
                sql = sql_file.read_text(encoding="utf-8")
                con.execute(sql)

        # Apply Marts Views
        marts_dir = MODELS_DIR / "marts"
        if marts_dir.exists():
            for sql_file in sorted(marts_dir.glob("*.sql")):
                sql = sql_file.read_text(encoding="utf-8")
                con.execute(sql)

    def execute_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        """Safely executes a read query and returns structured columns, rows, and execution stats."""
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise ValueError("Only read-only SELECT or WITH statements are permitted.")

        start_time = time.perf_counter()
        con = self.get_connection()
        cur = con.execute(sql, params or [])
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        description = cur.description or []
        columns = [d[0] for d in description]
        rows = cur.fetchall()

        # Convert non-serializable objects (datetime, date) to ISO strings
        clean_rows = []
        for row in rows:
            clean_row = []
            for item in row:
                if hasattr(item, "isoformat"):
                    clean_row.append(item.isoformat())
                else:
                    clean_row.append(item)
            clean_rows.append(clean_row)

        return {
            "columns": columns,
            "rows": clean_rows,
            "row_count": len(clean_rows),
            "duration_ms": duration_ms,
        }

    def get_filter_options(self) -> dict[str, Any]:
        """Returns available date boundaries, settlement periods, and fuel types."""
        con = self.get_connection()
        date_stats = con.execute("""
            SELECT 
                MIN(settlement_date)::TEXT as min_date,
                MAX(settlement_date)::TEXT as max_date,
                COUNT(DISTINCT settlement_date) as day_count
            FROM ods_generation_actual
        """).fetchone()

        fuels = [
            f[0]
            for f in con.execute("""
                SELECT DISTINCT fuel_type FROM ods_generation_actual ORDER BY fuel_type
            """).fetchall()
        ]

        table_counts = {}
        for tbl in ["raw_fuelinst", "raw_indo", "ods_generation_actual", "mart_generation_mix"]:
            cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            table_counts[tbl] = cnt

        return {
            "min_date": date_stats[0] if date_stats else "2024-03-01",
            "max_date": date_stats[1] if date_stats else "2024-03-07",
            "day_count": date_stats[2] if date_stats else 7,
            "fuel_types": fuels,
            "settlement_periods": list(range(1, 49)),
            "table_counts": table_counts,
        }

    def get_lineage(self) -> dict[str, Any]:
        """Loads and returns the DAG lineage metadata."""
        lineage_file = MODELS_DIR / "lineage.json"
        if lineage_file.exists():
            return json.loads(lineage_file.read_text(encoding="utf-8"))
        return {"nodes": [], "edges": []}


# Global singleton instance for easy import
_db_instance: PowerDeskDB | None = None


def get_db() -> PowerDeskDB:
    """Access the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PowerDeskDB()
    return _db_instance
