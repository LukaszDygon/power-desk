from datetime import date
from pathlib import Path
import re

import duckdb
import pytest

from power_desk_dashboard.queries import run_query
from power_desk_dashboard.widgets import load_widgets

STATIC = Path(__file__).parents[2] / "frontend" / "static"


@pytest.fixture
def warehouse_file(tmp_path: Path) -> Path:
    db = tmp_path / "w.duckdb"
    with duckdb.connect(str(db)) as con:
        for schema in ("marts", "ods", "dims", "raw"):
            con.execute(f"create schema {schema}")
        con.execute(
            "create table marts.days as select date '2024-03-01' + cast(i as integer) as day from range(3) t(i)"
        )
        con.execute(
            "create table dims.dim_area as select * from (values "
            "('10YFR-RTE------C', 'FR', 'France', true, true), "
            "('10YGB----------A', 'GB', 'Great Britain', true, true), "
            "('10YDE-VE-------2', 'DE-50HERTZ', 'Germany 50Hertz', true, false)"
            ") t(area_eic_code, display_name, long_name, is_current, is_bidding_zone)"
        )
    return db


def test_run_query_binds_only_the_dates_the_query_uses(warehouse_file):
    sql = "select count(*) from days where day >= $start_date"
    assert run_query(sql, start_date=date(2024, 3, 2), end_date=date(2024, 3, 3), db_path=warehouse_file)["rows"] == [
        [2]
    ]
    assert run_query("select 1", start_date=date(2024, 3, 2), db_path=warehouse_file)["rows"] == [[1]]


def test_run_query_binds_the_selected_areas_or_every_bidding_zone(warehouse_file):
    sql = "select unnest($areas) as area"
    assert run_query(sql, areas=["10YGB----------A"], db_path=warehouse_file)["rows"] == [["10YGB----------A"]]
    assert sorted(run_query(sql, db_path=warehouse_file)["rows"]) == [["10YFR-RTE------C"], ["10YGB----------A"]]


def test_run_query_can_only_read_the_warehouse(warehouse_file, tmp_path):
    with pytest.raises(duckdb.Error):
        run_query("drop table days", db_path=warehouse_file)
    with pytest.raises(duckdb.Error):
        run_query(f"select 1; copy (select 1) to '{tmp_path / 'out.csv'}'", db_path=warehouse_file)
    assert not (tmp_path / "out.csv").exists()


def palette() -> dict[str, str]:
    """chart-theme.js palette keys -> the dashboard.css variables they read."""
    theme = (STATIC / "js" / "chart-theme.js").read_text(encoding="utf-8")
    return dict(re.findall(r'^\s+([A-Z0-9_]+): cssVar\("(--[\w-]+)"\)', theme, re.MULTILINE))


def test_palette_keys_read_css_variables_that_exist():
    css = (STATIC / "css" / "dashboard.css").read_text(encoding="utf-8")
    assert palette() and [var for var in palette().values() if f"{var}:" not in css] == []


def test_widgets_are_valid_and_name_palette_colours():
    configs = [config for w in load_widgets() for config in [w.config, *(p.config for p in w.panels)]]
    colours = [
        colour
        for config in configs
        for colour in [
            *(series.get("color") for series in config.get("series", [])),
            config.get("color_positive"),
            config.get("color_negative"),
        ]
        if colour
    ]
    assert colours and [c for c in colours if c not in palette() and not c.startswith("#")] == []
