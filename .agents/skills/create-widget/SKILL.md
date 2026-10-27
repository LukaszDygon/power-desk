---
name: create-widget
description: >-
  Generates, validates, and registers a new analytical card/widget into the
  Power Desk GridStack dashboard, backed by a SQL query over the dbt marts / ods models.
---

# Create Widget Skill

Each dashboard card is a widget spec (stored in `data/widgets.json`): a DuckDB query plus a
visual config. Unqualified names resolve against the `marts`, `ods`, `dims` and `raw` schemas.

## 1. Find the data

Never assume relation or column names; read them from the catalogue:

```bash
uv run python -m power_desk.catalog.describe                # relations by layer, with descriptions
uv run python -m power_desk.catalog.describe <relation>     # columns, units and definitions
```

- Prefer `marts`: business marts (incremental, tested), or the `marts/combined` views for any area
  and source (one area level at a time); then `ods` entities.
- Avoid `staging` and `raw`: they are source-specific and may change.
- Join `dims` tables for labels and roll-ups (e.g. `bridge_*_hierarchy` to aggregate to a broader level).
- Columns starting with `_` are lineage metadata. Don't chart them.

## 2. Write the query

- Start with `SELECT` or `WITH`; anything else is rejected.
- Filter on the dashboard's global date range with the placeholders `'{start_date}'` and
  `'{end_date}'`, against the relation's date column.
- Order time series by their time column.

## 3. Pick a type and config

| `type` | Use for | `config` keys (defaults: first / second result column) |
|---|---|---|
| `line`, `stacked_area` | time series | `time_column`, `series: [{column, label, color?}]` |
| `bar` | categories, periods, deltas | `x_column`, `y_column` |
| `donut` | shares of a total | `label_column`, `value_column` |
| `kpi_cards` | headline numbers (one row) | `metrics: [{key, label, unit?, badge?, trend?}]` |
| `table` | dense inspection | `columns: [{key, label}]` (optional) |

`grid` sets the card's position and size on a 12-column grid: `{x, y, w, h}`.

Spec shape:

```json
{
  "id": "unique_slug",
  "title": "Card title",
  "type": "line",
  "description": "What the card shows",
  "grid": { "x": 0, "y": 0, "w": 6, "h": 4 },
  "sql": "SELECT <time_col>, <measure> FROM <relation> WHERE <date_col> >= '{start_date}' AND <date_col> <= '{end_date}' ORDER BY <time_col>",
  "config": { "time_column": "<time_col>", "series": [{ "column": "<measure>", "label": "<Label>" }] }
}
```

## 4. Register and validate

```bash
uv run power-desk-register-widget --json-file <spec.json>
# or: --id ... --title ... --type ... --sql ... --config '<json>' [--w 6 --h 4]
```

The script runs the query over the loaded date range and saves the spec only if it succeeds. The card then
appears on the dashboard, and in the lineage view as a consumer of the relations it queries.
