"""In-memory stand-in for the BMRS and PVLive APIs, backed by the seed generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from power_desk.ingest.seed import generate_seed_data

ENDPOINTS = {
    "/datasets/FUELINST": "raw_fuelinst",
    "/datasets/INDO": "raw_indo",
    "/datasets/ITSDO": "raw_itsdo",
    "/datasets/NDF": "raw_demand_forecast",
    "/datasets/WINDFOR": "raw_windfor",
}


class FakeApi:
    """Serves generated records filtered by the publish-time (BMRS) or datetime_gmt (PVLive) window."""

    def __init__(self, start_date: str, num_days: int, workdir: Path) -> None:
        generate_seed_data(start_date=start_date, num_days=num_days, output_dir=workdir)
        con = duckdb.connect()
        self.tables: dict[str, list[dict[str, Any]]] = {}
        for name in [*ENDPOINTS.values(), "raw_pvlive_solar"]:
            cur = con.execute(f"select * from read_parquet('{(workdir / f'{name}.parquet').as_posix()}')")
            cols = [d[0] for d in cur.description]
            self.tables[name] = [dict(zip(cols, row)) for row in cur.fetchall()]
        con.close()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def fetch_json(self, url: str, params: dict[str, Any] | None = None, timeout: int = 30, **headers: str) -> Any:
        params = params or {}
        self.calls.append((url, params))
        if "pvlive" in url:
            rows = [r for r in self.tables["raw_pvlive_solar"] if params["start"] <= r["datetime_gmt"] <= params["end"]]
            return {"meta": ["pes_id", "datetime_gmt", "generation_mw"],
                    "data": [[r["pes_id"], r["datetime_gmt"], r["generation_mw"]] for r in rows]}
        table = next(t for endpoint, t in ENDPOINTS.items() if url.endswith(endpoint))
        lo, hi = params["publishDateTimeFrom"], params["publishDateTimeTo"]
        return {"data": [dict(r) for r in self.tables[table] if lo <= r["publishTime"] <= hi]}
