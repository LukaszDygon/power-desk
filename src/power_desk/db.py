"""DuckDB access layer for the Power Desk dashboard.

The dashboard is read-only: dlt loads `raw`, dbt builds `ods` / `marts` / `dlt_meta`.
Queries resolve unqualified names against the marts, ods, dims and raw schemas.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any

import duckdb

from power_desk.ingest.pipelines import REPO_ROOT, warehouse_path

logger = logging.getLogger(__name__)

SEARCH_PATH = "marts,ods,dims,raw,main"
DEFAULT_MANIFEST = REPO_ROOT / "transform" / "target" / "manifest.json"
LINEAGE_LAYERS = {"staging": "staging_view", "ods": "ods_view", "marts": "mart_view"}


def manifest_path() -> Path:
    return Path(os.environ.get("POWER_DESK_DBT_MANIFEST", DEFAULT_MANIFEST))


class PowerDeskDB:
    """Read-only query engine over the dbt-managed DuckDB warehouse."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or warehouse_path())

    @contextmanager
    def connect(self, timeout: float = 10.0):
        """Yields a read-only DuckDB connection, retrying while dlt/dbt hold the write lock."""
        deadline = time.perf_counter() + timeout
        while True:
            try:
                con = duckdb.connect(database=self.db_path.as_posix(), read_only=True)
                break
            except (duckdb.IOException, duckdb.ConnectionException) as exc:
                if "lock" not in str(exc).lower() or time.perf_counter() >= deadline:
                    raise
                time.sleep(0.15)
        try:
            con.execute(f"SET search_path = '{SEARCH_PATH}';")
            yield con
        finally:
            con.close()

    def execute_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        """Safely executes a read query and returns structured columns, rows, and execution stats."""
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise ValueError("Only read-only SELECT or WITH statements are permitted.")

        start_time = time.perf_counter()
        with self.connect() as con:
            cur = con.execute(sql, params or [])
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            columns = [d[0] for d in cur.description or []]
            rows = cur.fetchall()

        # Convert non-serializable objects (datetime, date) to ISO strings
        clean_rows = [[item.isoformat() if hasattr(item, "isoformat") else item for item in row] for row in rows]
        return {
            "columns": columns,
            "rows": clean_rows,
            "row_count": len(clean_rows),
            "duration_ms": duration_ms,
        }

    def get_filter_options(self) -> dict[str, Any]:
        """Returns available date boundaries, settlement periods, and fuel types."""
        options: dict[str, Any] = {
            "min_date": "2024-03-01",
            "max_date": "2024-03-07",
            "day_count": 0,
            "fuel_types": [],
            "settlement_periods": list(range(1, 51)),
            "table_counts": {},
        }
        if not self.db_path.exists():
            return options

        with self.connect() as con:
            relations = {
                f"{schema}.{name}"
                for schema, name in con.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables"
                ).fetchall()
            }
            if "ods.ods_generation_actual" not in relations:
                return options

            min_date, max_date, day_count = con.execute("""
                SELECT MIN(settlement_date)::TEXT, MAX(settlement_date)::TEXT, COUNT(DISTINCT settlement_date)
                FROM marts.mart_generation_mix
            """).fetchone()
            options["fuel_types"] = [
                f[0] for f in con.execute(
                    "SELECT DISTINCT fuel_type FROM ods.ods_generation_actual ORDER BY fuel_type"
                ).fetchall()
            ]
            for rel in ["raw.raw_fuelinst", "raw.raw_indo", "ods.ods_generation_actual", "marts.mart_generation_mix"]:
                if rel in relations:
                    options["table_counts"][rel.split(".")[1]] = con.execute(f"SELECT COUNT(*) FROM {rel}").fetchone()[0]

        if min_date:
            options.update(min_date=min_date, max_date=max_date, day_count=day_count)
        return options

    def get_lineage(self) -> dict[str, Any]:
        """DAG for the lineage view, built from the dbt manifest and the widget registry."""
        path = manifest_path()
        if not path.exists():
            logger.warning("dbt manifest not found at %s; run `dbt parse` or `dbt build`", path)
            return {"nodes": [], "edges": []}
        return lineage_from_manifest(json.loads(path.read_text(encoding="utf-8")))


def plain_summary(description: str, paragraphs: int = 2) -> str:
    """First paragraphs of a (doc-block rendered) markdown description as plain text."""
    blocks = [p for p in re.split(r"\n\s*\n", description or "") if p.strip()]
    keep = [p for p in blocks if not p.lstrip().startswith((">", "Source:"))]
    if not keep:  # description made only of quoted provider definitions: use the quoted text
        quoted = re.sub(r"(?m)^> ?", "", "\n".join(blocks))
        keep = [p for p in re.split(r"\n\s*\n", quoted) if p.strip() and not p.lstrip().startswith("*")]
    text = " ".join(keep[:paragraphs])
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def lineage_from_manifest(manifest: dict[str, Any], widgets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """API source -> raw table (dlt) -> ODS view -> mart (dbt) -> dashboard widget."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    ids_by_unique_id: dict[str, str] = {}

    for unique_id, source in manifest.get("sources", {}).items():
        if source["source_name"] == "dlt":
            continue
        dlt_meta = source.get("config", {}).get("meta", {}).get("dlt", {}) or source.get("meta", {}).get("dlt", {})
        table = source["name"]
        api_id = f"api_{table}"
        nodes.append({
            "id": api_id,
            "label": f"{source['source_name'].upper()} API ({dlt_meta.get('resource', table)})",
            "type": "source",
            "desc": plain_summary(source.get("source_description", "")),
        })
        nodes.append({"id": table, "label": table, "type": "raw_table", "desc": plain_summary(source.get("description", ""))})
        edges.append({"source": api_id, "target": table, "label": f"dlt {dlt_meta.get('write_disposition', 'load')}"})
        ids_by_unique_id[unique_id] = table

    for unique_id, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "model" or node.get("schema") not in LINEAGE_LAYERS:
            continue
        nodes.append({
            "id": node["name"],
            "label": node["name"],
            "type": LINEAGE_LAYERS[node["schema"]],
            "desc": plain_summary(node.get("description", "")),
        })
        ids_by_unique_id[unique_id] = node["name"]

    for unique_id, node in manifest.get("nodes", {}).items():
        target = ids_by_unique_id.get(unique_id)
        if not target or node.get("resource_type") != "model":
            continue
        materialized = node.get("config", {}).get("materialized", "")
        for dep in node.get("depends_on", {}).get("nodes", []):
            if dep in ids_by_unique_id:
                edges.append({"source": ids_by_unique_id[dep], "target": target, "label": f"dbt {materialized}"})

    if widgets is None:
        from power_desk.widgets import load_widgets

        widgets = load_widgets()
    model_ids = {n["id"] for n in nodes if n["type"] in LINEAGE_LAYERS.values()}
    for widget in widgets:
        referenced = {m for m in re.findall(r"\b(?:from|join)\s+(?:\w+\.)?(\w+)", widget.get("sql", ""), re.I) if m in model_ids}
        if not referenced:
            continue
        widget_id = f"widget_{widget['id']}"
        nodes.append({"id": widget_id, "label": f"Widget: {widget['title']}", "type": "widget", "desc": widget.get("description", "")})
        edges.extend({"source": m, "target": widget_id, "label": "query"} for m in sorted(referenced))

    return {"nodes": nodes, "edges": edges}


# Global singleton instance for easy import
_db_instance: PowerDeskDB | None = None


def get_db() -> PowerDeskDB:
    """Access the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PowerDeskDB()
    return _db_instance
