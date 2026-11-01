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
- Avoid `staging` and `raw`: they are source-specific and may change. Data not yet in a mart or entity is
  onboarded first (the `onboard-source` skill).
- Join `dims` tables for labels and roll-ups (e.g. `bridge_*_hierarchy` to aggregate to a broader level).
- Columns starting with `_` are lineage metadata. Don't chart them.

## 2. Write the query

- Queries run read-only in a DuckDB sandbox: they can read the warehouse and nothing else.
- Every card shares the page's filter, bound as parameters (unquoted):
  - `$start_date`, `$end_date`: dates; on a timestamp, `timestamp_utc >= $start_date AND timestamp_utc < $end_date + INTERVAL 1 DAY`.
  - `$areas`: EIC codes of the bidding zones selected on the zone map, in selection order (every bidding
    zone when none is selected): `list_contains($areas, area_eic_code)`. Sum over zones; never mix area levels.
  - `$bucket`: an interval sized to the date range (hourly up to two weeks, then 6-hourly, daily, weekly):
    `time_bucket($bucket, timestamp_utc)`.
- Time series return a row for every bucket of the range (generate the grid with
  `generate_series(time_bucket($bucket, $start_date::TIMESTAMP), $end_date::TIMESTAMP + INTERVAL 1 DAY - INTERVAL 1 MICROSECOND, $bucket)`),
  ordered by time, so missing buckets are explicit. Zeros are data; null is unknown.
- Summed over zones: sum the zones that report, and add the coverage columns `zones_reporting`,
  `zones_expected` (selected zones with any data for the measure in the range) and `zones_missing` (names).
  The chart shades a bucket light grey when some zones are missing and darker grey when none reports, and
  names the missing zones in its tooltip. The `market` card's panel queries show the pattern.

## 3. Pick a type and config

| `type` | Use for | `config` keys (defaults: first / second result column) |
|---|---|---|
| `line`, `stacked_area` | time series | `time_column`, `series: [{column, label, color?, borderDash?}]`, `y_title?` (default `MW`); or long rows with `series_column`, `value_column`, `max_series?` (one series per value, in order of first appearance) |
| `bar` | categories, periods, deltas | `x_column`, `y_column`, `x_label_prefix?`, `y_title?` (default `MW`), `color_positive?`, `color_negative?` |
| `donut` | shares of a total | `label_column`, `value_column` |
| `kpi_cards` | headline numbers (one row) | `metrics: [{key, label, unit?, badge?, trend?}]` |
| `table` | dense inspection | `columns: [{key, label}]` (optional) |
| `area_map` | per-zone values; its clicks set `$areas` | `area_column` (EIC code), `metrics: [{key, label, unit?}]` (shading choices); don't filter it on `$areas` |
| `panels` | several time series on one time axis, toggled in the header | `panels: [{id, title, type (line / stacked_area), sql, config}]` instead of `sql`; `config.default_panels` |

Line options: `fill_to` on a series with `spread_fill: {above, below}` shades the spread between two
series by its sign; `fill_origin: {above, below}` shades a series against zero; `band: {lower, upper}`
draws two series as a band; `empty_message` replaces the default "no data" text.

Colours (`color`, `color_positive`, `color_negative`) name the energy palette (`WIND`, `SOLAR`, `NUCLEAR`,
`CCGT`, `BIOMASS`, `HYDRO`, `STORAGE`, `COAL`, `IMPORTS`, `DEMAND_ACTUAL`, `DEMAND_FORECAST`, `DELTA_POSITIVE`,
`DELTA_NEGATIVE`, and `SERIES_1`…`SERIES_8` for series that are not fuels; keys in `static/js/chart-theme.js`,
values in `dashboard.css` `:root`) or give any CSS colour. Stacked series named by `series_column` take their
fuel's colour; line series take `SERIES_*` in order.

`grid` sets the card's position and size on a 12-column grid: `{x, y, w, h}`.

Spec shape:

```json
{
  "id": "unique_slug",
  "title": "Card title",
  "type": "line",
  "description": "What the card shows",
  "grid": { "x": 0, "y": 0, "w": 6, "h": 4 },
  "sql": "SELECT <time_col>, <measure> FROM <relation> WHERE <date_col> >= $start_date AND <date_col> <= $end_date ORDER BY <time_col>",
  "config": { "time_column": "<time_col>", "series": [{ "column": "<measure>", "label": "<Label>" }] }
}
```

## 4. Register and validate

```bash
uv run power-desk-register-widget --json-file <spec.json>
# or: --id ... --title ... --type ... --sql ... --config '<json>' [--w 6 --h 4]
```

The script runs the query over the loaded date range and every bidding zone, and saves the spec only if it
succeeds. To ship a card to fresh checkouts, copy it into `src/power_desk/dashboard/default_widgets.json`. The card then
appears on the dashboard, and in the lineage view as a consumer of the relations it queries.
