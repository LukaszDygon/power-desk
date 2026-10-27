"""dlt loads pending for the tracked marts (`meta.dlt_tracked`).

A completed load (`raw._dlt_loads.status = 0`) is pending until `dlt_meta.dlt_load_audit` records
it for every tracked mart. Reads tables only: dbt's views embed the DuckDB catalog name and break
when the warehouse file is renamed, until dbt rebuilds them.
"""

from __future__ import annotations

import json
from pathlib import Path

from power_desk import warehouse
from power_desk.settings import dbt_manifest_path, warehouse_path


def tracked_models(manifest: Path | None = None) -> list[str]:
    path = manifest or dbt_manifest_path()
    if not path.exists():
        return []
    nodes = json.loads(path.read_text(encoding="utf-8"))["nodes"].values()
    return sorted(
        n.get("alias") or n["name"]
        for n in nodes
        if n["resource_type"] == "model" and (n.get("config", {}).get("meta") or {}).get("dlt_tracked")
    )


def pending_load_ids(db_path: Path | str | None = None) -> list[str]:
    path = Path(db_path or warehouse_path())
    if not path.exists():
        return []
    with warehouse.connect(path) as con:
        if "_dlt_loads" not in warehouse.table_names(con, "raw", base_tables_only=True):
            return []
        tracked = tracked_models()
        audited = tracked and "dlt_load_audit" in warehouse.table_names(con, "dlt_meta", base_tables_only=True)
        if not audited:
            return [
                row[0]
                for row in con.execute("select load_id from raw._dlt_loads where status = 0 order by 1").fetchall()
            ]
        return [
            row[0]
            for row in con.execute(
                f"""
            select l.load_id from raw._dlt_loads l
            where l.status = 0
              and (select count(distinct a.model_name) from dlt_meta.dlt_load_audit a
                   where a.load_id = l.load_id and a.model_name in ({", ".join("?" for _ in tracked)})) < ?
            order by l.load_id
        """,
                [*tracked, len(tracked)],
            ).fetchall()
        ]
