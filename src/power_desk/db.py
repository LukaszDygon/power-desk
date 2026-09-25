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


def load_seed_with_dlt(db_path: Path | str, dataset_name: str = "raw") -> None:
    """Loads seed parquet files via dlt to ensure tables have native dlt schema & metadata."""
    import dlt

    seed_resources = []
    resource_defs = [
        ("raw_fuelinst", ["settlement_date", "settlement_period", "fuel_type", "start_time"]),
        ("raw_indo", ["settlement_date", "settlement_period"]),
        ("raw_demand_forecast", ["settlement_date", "settlement_period", "boundary", "publish_time"]),
        ("raw_windfor", ["start_time", "publish_time"]),
    ]

    for tbl_name, pk in resource_defs:
        p_file = SEED_DIR / f"{tbl_name}.parquet"
        if p_file.exists():
            def make_res(name=tbl_name, path=p_file, keys=pk):
                @dlt.resource(name=name, write_disposition="merge", primary_key=keys)
                def _res():
                    temp_con = duckdb.connect()
                    desc = temp_con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')").description
                    cols = [d[0] for d in desc]
                    rows = temp_con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}')").fetchall()
                    temp_con.close()
                    yield [dict(zip(cols, r)) for r in rows]
                return _res
            seed_resources.append(make_res()())

    if seed_resources:
        pipeline = dlt.pipeline(
            pipeline_name="bmrs_backfill",
            destination=dlt.destinations.duckdb(str(db_path)),
            dataset_name=dataset_name,
        )
        try:
            pipeline.abort_packages()
        except Exception:
            pass
        pipeline.run(seed_resources)


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
            self._con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
            self._con.execute("SET search_path = 'raw,main';")
        return self._con

    def initialize(self) -> None:
        """Initializes raw tables from seed parquet if not present, and registers all views."""
        con = self.get_connection()

        # Check if dlt tables exist in raw schema
        tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'").fetchall()
        existing_tables = {t[0] for t in tables}

        if "_dlt_version" not in existing_tables or "raw_fuelinst" not in existing_tables:
            # Drop incomplete non-dlt tables if any exist
            for tbl in ["raw_fuelinst", "raw_indo", "raw_itsdo", "raw_demand_forecast", "raw_windfor"]:
                if tbl in existing_tables:
                    con.execute(f"DROP TABLE IF EXISTS raw.{tbl};")
            # Close connection temporarily while dlt pipeline writes
            if self._con:
                self._con.close()
                self._con = None
            load_seed_with_dlt(self.db_path)
            con = self.get_connection()

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
