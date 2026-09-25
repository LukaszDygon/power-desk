"""DuckDB Database Manager for Power Desk.

Manages connections, automated loading of seed/parquet tables, execution of
DBT-style ODS & Marts SQL views, and read-only parameterized query execution.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
from pathlib import Path
import time
from typing import Any

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
        self.initialize()

    @contextmanager
    def connect(self, read_only: bool = True, timeout: float = 10.0):
        """Yields a managed DuckDB connection with automatic retry on concurrent lock contention."""
        deadline = time.perf_counter() + timeout
        con = None
        if read_only and not self.db_path.exists():
            try:
                init_con = duckdb.connect(database=self.db_path.as_posix(), read_only=False)
                init_con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
                init_con.close()
            except Exception:
                pass

        while time.perf_counter() < deadline:
            try:
                con = duckdb.connect(database=self.db_path.as_posix(), read_only=read_only)
                if not read_only:
                    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
                con.execute("SET search_path = 'raw,main';")
                break
            except (duckdb.IOException, duckdb.ConnectionException) as exc:
                if "lock" in str(exc).lower():
                    time.sleep(0.15)
                    continue
                raise
        if con is None:
            con = duckdb.connect(database=self.db_path.as_posix(), read_only=read_only)
            if not read_only:
                con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
            con.execute("SET search_path = 'raw,main';")

        try:
            yield con
        finally:
            try:
                con.close()
            except Exception:
                pass

    def get_connection(self, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        """Returns a standalone open connection (caller must close when finished)."""
        con = duckdb.connect(database=self.db_path.as_posix(), read_only=read_only)
        if not read_only:
            con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        con.execute("SET search_path = 'raw,main';")
        return con

    def initialize_views(self) -> None:
        """Applies ODS and Marts SQL views to the database if base tables exist."""
        if not self.db_path.exists():
            return

        with self.connect(read_only=False, timeout=15.0) as con:
            con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
            tables = {
                t[0]
                for t in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
                ).fetchall()
            }

            if not ("raw_fuelinst" in tables or "raw_indo" in tables):
                logger.info("Raw tables not loaded yet; skipping SQL view creation.")
                return

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

    def initialize(self) -> None:
        """Lightweight startup initialization for the server. Does NOT load any data."""
        self.initialize_views()

    def execute_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        """Safely executes a read query and returns structured columns, rows, and execution stats."""
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise ValueError("Only read-only SELECT or WITH statements are permitted.")

        start_time = time.perf_counter()
        with self.connect(read_only=True, timeout=10.0) as con:
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
        default_options = {
            "min_date": "2024-03-01",
            "max_date": "2024-03-07",
            "day_count": 0,
            "fuel_types": [],
            "settlement_periods": list(range(1, 49)),
            "table_counts": {},
        }
        if not self.db_path.exists():
            return default_options

        with self.connect(read_only=True, timeout=10.0) as con:
            tables = {
                t[0]
                for t in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
                ).fetchall()
            }
            if "ods_generation_actual" not in tables:
                return default_options

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
                if tbl in tables:
                    cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    table_counts[tbl] = cnt

        return {
            "min_date": date_stats[0] if (date_stats and date_stats[0]) else "2024-03-01",
            "max_date": date_stats[1] if (date_stats and date_stats[1]) else "2024-03-07",
            "day_count": date_stats[2] if (date_stats and date_stats[2]) else 0,
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
