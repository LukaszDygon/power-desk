from datetime import date
from pathlib import Path
import re

import duckdb
import pytest

from power_desk.dashboard.lineage import lineage_from_manifest
from power_desk.dashboard.queries import run_query
from power_desk.dashboard.widgets import DEFAULTS, Widget, load_widgets

STATIC = Path(__file__).parents[2] / "src" / "power_desk" / "dashboard" / "static"

MANIFEST = {
    "sources": {
        "source.p.bmrs.bmrs__indo": {
            "source_name": "bmrs",
            "name": "bmrs__indo",
            "description": "INDO",
            "config": {"meta": {"dlt": {"resource": "bmrs__indo", "write_disposition": "merge"}}},
        }
    },
    "nodes": {
        "model.p.stg_bmrs__indo": {
            "resource_type": "model",
            "name": "stg_bmrs__indo",
            "schema": "staging",
            "depends_on": {"nodes": ["source.p.bmrs.bmrs__indo"]},
            "config": {"materialized": "view"},
        },
        "model.p.mart_demand_actual": {
            "resource_type": "model",
            "name": "mart_demand_actual",
            "schema": "marts",
            "depends_on": {"nodes": ["model.p.stg_bmrs__indo"]},
            "config": {"materialized": "view"},
        },
    },
}


@pytest.fixture
def warehouse_file(tmp_path: Path) -> Path:
    db = tmp_path / "w.duckdb"
    with duckdb.connect(str(db)) as con:
        for schema in ("marts", "ods", "dims", "raw"):
            con.execute(f"create schema {schema}")
        con.execute(
            "create table marts.days as select date '2024-03-01' + cast(i as integer) as day from range(3) t(i)"
        )
    return db


def test_run_query_binds_only_the_dates_the_query_uses(warehouse_file):
    sql = "select count(*) from days where day >= $start_date"
    assert run_query(sql, start_date=date(2024, 3, 2), end_date=date(2024, 3, 3), db_path=warehouse_file)["rows"] == [
        [2]
    ]
    assert run_query("select 1", start_date=date(2024, 3, 2), db_path=warehouse_file)["rows"] == [[1]]


def test_run_query_can_only_read_the_warehouse(warehouse_file, tmp_path):
    with pytest.raises(duckdb.Error):
        run_query("drop table days", db_path=warehouse_file)
    with pytest.raises(duckdb.Error):
        run_query(f"select 1; copy (select 1) to '{tmp_path / 'out.csv'}'", db_path=warehouse_file)
    assert not (tmp_path / "out.csv").exists()


def test_lineage_links_publisher_raw_models_and_widgets():
    widgets = [Widget(id="w", title="W", sql="select * from marts.mart_demand_actual")]
    graph = lineage_from_manifest(MANIFEST, widgets)
    assert {(e["source"], e["target"]) for e in graph["edges"]} == {
        ("api_bmrs__indo", "bmrs__indo"),
        ("bmrs__indo", "stg_bmrs__indo"),
        ("stg_bmrs__indo", "mart_demand_actual"),
        ("mart_demand_actual", "widget_w"),
    }


def palette() -> dict[str, str]:
    """chart-theme.js palette keys -> the dashboard.css variables they read."""
    theme = (STATIC / "js" / "chart-theme.js").read_text(encoding="utf-8")
    return dict(re.findall(r'^\s+([A-Z_]+): cssVar\("(--[\w-]+)"\)', theme, re.MULTILINE))


def test_palette_keys_read_css_variables_that_exist():
    css = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert palette() and [var for var in palette().values() if f"{var}:" not in css] == []


def test_default_widgets_are_valid_and_name_palette_colours():
    colours = [
        colour
        for widget in load_widgets(DEFAULTS)
        for colour in [
            *(series.get("color") for series in widget.config.get("series", [])),
            widget.config.get("color_positive"),
            widget.config.get("color_negative"),
        ]
        if colour
    ]
    assert colours and [c for c in colours if c not in palette() and not c.startswith("#")] == []
