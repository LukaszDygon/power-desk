from pathlib import Path
import re

import pytest

from power_desk.dashboard.lineage import lineage_from_manifest
from power_desk.dashboard.queries import bind_dates, run_query
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


def test_bind_dates_accepts_iso_dates_only():
    assert bind_dates("where d >= '{start_date}'", start_date="2024-03-01") == "where d >= '2024-03-01'"
    with pytest.raises(ValueError):
        bind_dates("where d >= '{start_date}'", start_date="2024-03-01' or 1=1 --")


def test_run_query_rejects_statements_other_than_select():
    with pytest.raises(ValueError, match="only SELECT"):
        run_query("drop table raw.bmrs__indo")


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
