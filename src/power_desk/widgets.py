"""Widget manager and registry for Power Desk dashboard.

Widgets represent analytical cards positioned on the GridStack.js grid,
backed by SQL queries against DuckDB ODS and Marts views.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WIDGETS_FILE = REPO_ROOT / "data" / "widgets.json"


class GridPosition(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 4
    minW: int = 3
    minH: int = 2


class WidgetSpec(BaseModel):
    id: str
    title: str
    type: str  # "stacked_area", "line", "donut", "kpi_cards", "table"
    sql: str
    grid: GridPosition = Field(default_factory=GridPosition)
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


DEFAULT_WIDGETS: list[dict[str, Any]] = [
    {
        "id": "kpi_grid_overview",
        "title": "Grid Operational Overview",
        "type": "kpi_cards",
        "description": "High-level real-time and aggregate power KPIs",
        "grid": { "x": 0, "y": 0, "w": 12, "h": 2, "minW": 6, "minH": 2 },
        "sql": """
            SELECT 
                ROUND(AVG(avg_clean_share_pct), 1) as avg_clean_share,
                ROUND(MAX(peak_demand_mw)) as max_peak_demand,
                ROUND(AVG(avg_wind_mw)) as avg_wind_mw,
                ROUND(AVG(avg_solar_mw)) as avg_solar_mw,
                ROUND(AVG(avg_demand_mw)) as avg_demand_mw
            FROM mart_hourly_summary
            WHERE date_utc >= '{start_date}' AND date_utc <= '{end_date}'
        """,
        "config": {
            "metrics": [
                { "key": "avg_clean_share", "label": "Zero-Carbon Share", "unit": "%", "trend": "positive", "badge": "ESG" },
                { "key": "max_peak_demand", "label": "Peak Demand", "unit": "MW", "trend": "neutral", "badge": "LOAD" },
                { "key": "avg_wind_mw", "label": "Avg Wind Output", "unit": "MW", "trend": "positive", "badge": "RENEWABLE" },
                { "key": "avg_solar_mw", "label": "Avg Solar Output", "unit": "MW", "trend": "neutral", "badge": "SOLAR" },
                { "key": "avg_demand_mw", "label": "System Baseload", "unit": "MW", "trend": "neutral", "badge": "INDO" }
            ]
        }
    },
    {
        "id": "generation_mix_timeseries",
        "title": "Power Generation Mix by Fuel (MW)",
        "type": "stacked_area",
        "description": "Half-hourly generation stacked by primary fuel sources",
        "grid": { "x": 0, "y": 2, "w": 8, "h": 5, "minW": 4, "minH": 3 },
        "sql": """
            SELECT 
                timestamp_utc,
                wind_mw,
                solar_mw,
                nuclear_mw,
                ccgt_gas_mw,
                biomass_mw,
                hydro_mw,
                imports_mw
            FROM mart_generation_mix
            WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}'
            ORDER BY timestamp_utc ASC
        """,
        "config": {
            "time_column": "timestamp_utc",
            "series": [
                { "column": "wind_mw", "label": "Wind", "color": "#00e5a3" },
                { "column": "solar_mw", "label": "Solar", "color": "#f59e0b" },
                { "column": "nuclear_mw", "label": "Nuclear", "color": "#818cf8" },
                { "column": "biomass_mw", "label": "Biomass", "color": "#84cc16" },
                { "column": "hydro_mw", "label": "Hydro / PS", "color": "#0ea5e9" },
                { "column": "ccgt_gas_mw", "label": "CCGT Gas", "color": "#f97316" },
                { "column": "imports_mw", "label": "Interconnectors", "color": "#94a3b8" }
            ]
        }
    },
    {
        "id": "fuel_share_donut",
        "title": "Total Generation Share",
        "type": "donut",
        "description": "Total energy contribution by fuel type for the selected window",
        "grid": { "x": 8, "y": 2, "w": 4, "h": 5, "minW": 3, "minH": 3 },
        "sql": """
            SELECT 
                fuel_type,
                ROUND(SUM(generation_mw), 1) as total_mwh
            FROM ods_generation_actual
            WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}'
            GROUP BY fuel_type
            ORDER BY total_mwh DESC
        """,
        "config": {
            "label_column": "fuel_type",
            "value_column": "total_mwh"
        }
    },
    {
        "id": "demand_vs_forecast_line",
        "title": "National Demand: Outturn vs Day-Ahead Forecast",
        "type": "line",
        "description": "Actual transmission system demand (INDO) compared against forecast",
        "grid": { "x": 0, "y": 7, "w": 8, "h": 5, "minW": 4, "minH": 3 },
        "sql": """
            SELECT 
                timestamp_utc,
                actual_demand_mw,
                forecast_demand_mw,
                delta_mw
            FROM mart_demand_vs_forecast
            WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}'
            ORDER BY timestamp_utc ASC
        """,
        "config": {
            "time_column": "timestamp_utc",
            "series": [
                { "column": "actual_demand_mw", "label": "Actual Demand (MW)", "color": "#f8fafc", "borderWidth": 2 },
                { "column": "forecast_demand_mw", "label": "Day-Ahead Forecast (MW)", "color": "#c084fc", "borderWidth": 2, "borderDash": [4, 4] }
            ]
        }
    },
    {
        "id": "forecast_variance_bar",
        "title": "Forecast Imbalance Variance (Delta MW)",
        "type": "bar",
        "description": "Over/under forecasting delta across settlement periods",
        "grid": { "x": 8, "y": 7, "w": 4, "h": 5, "minW": 3, "minH": 3 },
        "sql": """
            SELECT 
                settlement_period,
                ROUND(AVG(delta_mw), 1) as avg_delta_mw
            FROM mart_demand_vs_forecast
            WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}'
            GROUP BY settlement_period
            ORDER BY settlement_period ASC
        """,
        "config": {
            "x_column": "settlement_period",
            "y_column": "avg_delta_mw",
            "color_positive": "#34d399",
            "color_negative": "#f43f5e"
        }
    },
    {
        "id": "hourly_analyst_table",
        "title": "Hourly Power Desk Settlement Rollup",
        "type": "table",
        "description": "High-density tabular ledger of hourly system dispatch and clean shares",
        "grid": { "x": 0, "y": 12, "w": 12, "h": 4, "minW": 6, "minH": 3 },
        "sql": """
            SELECT 
                hour_utc,
                avg_demand_mw,
                avg_forecast_demand_mw,
                avg_generation_mw,
                avg_wind_mw,
                avg_solar_mw,
                avg_gas_mw,
                avg_clean_share_pct
            FROM mart_hourly_summary
            WHERE date_utc >= '{start_date}' AND date_utc <= '{end_date}'
            ORDER BY hour_utc DESC
            LIMIT 48
        """,
        "config": {
            "columns": [
                { "key": "hour_utc", "label": "Hour (UTC)" },
                { "key": "avg_demand_mw", "label": "Demand (MW)" },
                { "key": "avg_forecast_demand_mw", "label": "Forecast (MW)" },
                { "key": "avg_generation_mw", "label": "Gen Total (MW)" },
                { "key": "avg_wind_mw", "label": "Wind (MW)" },
                { "key": "avg_solar_mw", "label": "Solar (MW)" },
                { "key": "avg_gas_mw", "label": "CCGT (MW)" },
                { "key": "avg_clean_share_pct", "label": "Clean %" }
            ]
        }
    }
]


def load_widgets(filepath: Path | str | None = None) -> list[dict[str, Any]]:
    """Loads all registered dashboard widgets from JSON file or writes defaults."""
    path = Path(filepath or WIDGETS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_widgets(DEFAULT_WIDGETS, path)
        return DEFAULT_WIDGETS
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_WIDGETS


def save_widgets(widgets: list[dict[str, Any]], filepath: Path | str | None = None) -> None:
    """Saves widgets list to disk."""
    path = Path(filepath or WIDGETS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(widgets, indent=2), encoding="utf-8")


def add_or_update_widget(widget: dict[str, Any], filepath: Path | str | None = None) -> list[dict[str, Any]]:
    """Adds a new widget or updates existing one by id."""
    widgets = load_widgets(filepath)
    w_id = widget.get("id")
    updated = False
    for i, w in enumerate(widgets):
        if w.get("id") == w_id:
            widgets[i] = widget
            updated = True
            break
    if not updated:
        widgets.append(widget)
    save_widgets(widgets, filepath)
    return widgets


def remove_widget(widget_id: str, filepath: Path | str | None = None) -> list[dict[str, Any]]:
    """Removes a widget by id."""
    widgets = load_widgets(filepath)
    widgets = [w for w in widgets if w.get("id") != widget_id]
    save_widgets(widgets, filepath)
    return widgets
