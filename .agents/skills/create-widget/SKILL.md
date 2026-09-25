---
name: create-widget
description: >-
  Generates, validates, and registers a new analytical card/widget into the
  Power Desk GridStack dashboard backed by DuckDB ODS and Marts views.
---

# Create Widget Skill

Allows an AI agent to build a new interactive analytical card in the **Power Desk** dashboard.

## Overview
Power Desk uses a high-density, resizable grid layout (GridStack.js) where each card executes a DuckDB query against the clean ODS or Marts views.

Available Views to query:
- `mart_generation_mix`: `timestamp_utc`, `settlement_date`, `settlement_period`, `wind_mw`, `solar_mw`, `nuclear_mw`, `ccgt_gas_mw`, `biomass_mw`, `hydro_mw`, `coal_mw`, `imports_mw`, `total_generation_mw`, `clean_share_pct`
- `mart_demand_vs_forecast`: `timestamp_utc`, `settlement_date`, `settlement_period`, `actual_demand_mw`, `forecast_demand_mw`, `delta_mw`, `absolute_error_pct`
- `mart_hourly_summary`: `hour_utc`, `date_utc`, `avg_demand_mw`, `avg_forecast_demand_mw`, `avg_generation_mw`, `avg_wind_mw`, `avg_solar_mw`, `avg_nuclear_mw`, `avg_gas_mw`, `avg_clean_share_pct`, `peak_demand_mw`, `min_demand_mw`
- `ods_generation_actual`: `timestamp_utc`, `settlement_date`, `settlement_period`, `fuel_type`, `generation_mw`, `publish_time_utc`
- `ods_demand_actual`: `timestamp_utc`, `settlement_date`, `settlement_period`, `national_demand_mw`

## Widget Types & Configs

### 1. `stacked_area` (or `line`)
Time-series charts using Chart.js with functional energy colors:
```json
{
  "id": "my_timeseries",
  "title": "Clean Generation Breakdown",
  "type": "stacked_area",
  "grid": { "x": 0, "y": 0, "w": 6, "h": 4 },
  "sql": "SELECT timestamp_utc, wind_mw, solar_mw, nuclear_mw FROM mart_generation_mix WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}' ORDER BY timestamp_utc ASC",
  "config": {
    "time_column": "timestamp_utc",
    "series": [
      { "column": "wind_mw", "label": "Wind", "color": "#00e5a3" },
      { "column": "solar_mw", "label": "Solar", "color": "#f59e0b" },
      { "column": "nuclear_mw", "label": "Nuclear", "color": "#818cf8" }
    ]
  }
}
```

### 2. `bar`
Variance, delta, or discrete period comparisons:
```json
{
  "id": "period_variance",
  "title": "Peak Imbalance by Period",
  "type": "bar",
  "grid": { "x": 6, "y": 0, "w": 6, "h": 4 },
  "sql": "SELECT settlement_period, ROUND(AVG(delta_mw), 1) as avg_delta FROM mart_demand_vs_forecast WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}' GROUP BY settlement_period ORDER BY settlement_period",
  "config": {
    "x_column": "settlement_period",
    "y_column": "avg_delta"
  }
}
```

### 3. `donut`
Categorical share / fuel mix breakdown:
```json
{
  "id": "fuel_donut",
  "title": "Energy Mix",
  "type": "donut",
  "grid": { "x": 0, "y": 0, "w": 4, "h": 4 },
  "sql": "SELECT fuel_type, SUM(generation_mw) as total FROM ods_generation_actual WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}' GROUP BY fuel_type",
  "config": {
    "label_column": "fuel_type",
    "value_column": "total"
  }
}
```

### 4. `kpi_cards`
Top-level metrics with units and badges:
```json
{
  "id": "grid_kpis",
  "title": "System Summary",
  "type": "kpi_cards",
  "grid": { "x": 0, "y": 0, "w": 12, "h": 2 },
  "sql": "SELECT ROUND(AVG(clean_share_pct), 1) as clean_pct, ROUND(MAX(total_generation_mw)) as max_gen FROM mart_generation_mix WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}'",
  "config": {
    "metrics": [
      { "key": "clean_pct", "label": "Zero-Carbon Share", "unit": "%", "badge": "ESG" },
      { "key": "max_gen", "label": "Peak Generation", "unit": "MW", "badge": "GRID" }
    ]
  }
}
```

### 5. `table`
High-density tabular ledger:
```json
{
  "id": "recent_records",
  "title": "Latest Dispatches",
  "type": "table",
  "grid": { "x": 0, "y": 0, "w": 12, "h": 4 },
  "sql": "SELECT hour_utc, avg_demand_mw, avg_generation_mw, avg_clean_share_pct FROM mart_hourly_summary WHERE date_utc >= '{start_date}' AND date_utc <= '{end_date}' ORDER BY hour_utc DESC LIMIT 20",
  "config": {
    "columns": [
      { "key": "hour_utc", "label": "Hour (UTC)" },
      { "key": "avg_demand_mw", "label": "Demand (MW)" },
      { "key": "avg_generation_mw", "label": "Generation (MW)" },
      { "key": "avg_clean_share_pct", "label": "Clean %" }
    ]
  }
}
```

## Workflow

1. **Design the SQL Query**:
   Target `mart_*` or `ods_*` views. Always include date placeholders `{start_date}` and `{end_date}` so the widget reacts to the dashboard's global filter bar.
2. **Select the Visualization**:
   Choose the appropriate widget type and define the `config` field mappings.
3. **Register & Validate**:
   Run the CLI validator to ensure the SQL query is valid before saving:
   ```bash
   uv run python scripts/register_widget.py --json-file <path_to_widget_spec.json>
   ```
   Or pass parameters directly:
   ```bash
   uv run python scripts/register_widget.py \
     --id "solar_curtailment_est" \
     --title "Solar vs Gas Daytime Co-generation" \
     --type "line" \
     --sql "SELECT timestamp_utc, solar_mw, ccgt_gas_mw FROM mart_generation_mix WHERE settlement_date >= '{start_date}' AND settlement_date <= '{end_date}' ORDER BY timestamp_utc"
   ```
4. **Confirm**:
   The widget is immediately persisted into `data/widgets.json` and rendered in the dashboard.
