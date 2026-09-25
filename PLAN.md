# Power Desk — Implementation Plan & Progress Tracker

**Power Desk** is a minimalist analyst dashboard for UK Power & Energy Data.
Built with DuckDB, `dlt` (data load tool), DBT-style SQL transformation views (Raw $\to$ ODS $\to$ Marts), GridStack.js resizable card grid, Cytoscape.js lineage graph, and an AI agent skill for on-the-fly analytical widget generation.

---

## Progress Overview

- [x] **Milestone 0: Spec & Architecture Approval**
  - [x] Defined minimal analyst dashboard requirements & visual style
  - [x] Confirmed `dlt` incremental merge + raw data preservation
  - [x] Confirmed DBT ODS & Marts as SQL views with settlement date/period to UTC natural keys
  - [x] Confirmed GridStack.js, Cytoscape.js lineage, and agent `create-widget` skill

- [x] **Milestone 1: Repository Setup & Foundations**
  - [x] Initialize git repo, `.gitignore`, `.python-version`
  - [x] Configure `pyproject.toml` with `uv` (`dlt`, `duckdb`, `fastapi`, `uvicorn`, `pytest`)
  - [x] Lock dependencies via `uv sync`

- [x] **Milestone 2: Elexon BMRS `dlt` Source Builder**
  - [x] Implement `sources/bmrs.py` with custom `dlt` source generator
  - [x] Configure incremental loading with merge write disposition on Natural Key
  - [x] Preserve raw API fields without python-level row mutations
  - [x] Cover generation actuals (B1620/FUELINST), demand (INDO/ITSDO), and day-ahead forecasts
  - [x] Support configurable start date (backfillable to 2021)

- [x] **Milestone 3: DBT / DuckDB Transformations (ODS & Marts Views)**
  - [x] Implement settlement period (1-48/50) $\to$ UTC timestamp converter logic in DuckDB SQL
  - [x] Create ODS views (`ods_generation_actual`, `ods_demand_actual`, `ods_demand_forecast`, etc.)
  - [x] Create Marts views (`mart_generation_mix`, `mart_demand_vs_forecast`, `mart_hourly_summary`)
  - [x] Bundle curated realistic seed partition for instant exploration without live API keys
  - [x] Test SQL views against DuckDB

- [x] **Milestone 4: Backend API & Query Engine**
  - [x] Implement `db.py` for DuckDB connection, view execution, and query filtering
  - [x] Build FastAPI server (`app.py`) with:
    - `/` (Analyst dashboard frontend)
    - `/api/query` (Safe parameterized SQL execution for widgets)
    - `/api/lineage` (DAG nodes & edges for Cytoscape.js)
    - `/api/filters` (Available date ranges, settlement periods, fuels)
    - `/api/widgets` (GET / POST widget catalog)

- [x] **Milestone 5: Minimalist Analyst Frontend**
  - [x] Unique typography: Cabinet Grotesk, Geist, Commit Mono
  - [x] High-density dark terminal theme (clean slate `#0b0f17`, subtle borders, zero clutter)
  - [x] GridStack.js drag-and-resize responsive grid with local layout persistence
  - [x] Functional Energy Color Palette for Chart.js (Wind=Cyan, Solar=Gold, Nuclear=Indigo, Gas=Ember, Demand=Signal White, Forecast=Dashed Violet)
  - [x] Interactive Cytoscape.js + Dagre open-source lineage modal / drawer
  - [x] Global & Card filter bar (date range, period, fuel toggles)

- [x] **Milestone 6: Agent Skill (`create-widget`)**
  - [x] Create `.agents/skills/create-widget/SKILL.md`
  - [x] Document schema, widget types (line, stacked area, bar, kpi, table), and registration workflow
  - [x] Include verification script / CLI helper (`scripts/register_widget.py`) to test newly created widgets

- [x] **Milestone 7: Verification & Test Suite**
  - [x] Comprehensive `pytest` test suite (14 passing tests):
    - Test `dlt` source configuration & incremental cursor
    - Test settlement period to UTC mapping (standard GMT and BST offsets)
    - Test API endpoints and widget queries
  - [x] Verified dev server boot, static assets, and widget lifecycle

- [x] **Milestone 8: Incremental Backfill CLI & Full Refresh**
  - [x] Implement `scripts/backfill.py` CLI supporting `--start-date`, `--end-date`, `--resources`, and `--full-refresh`
  - [x] Support bounded backfill mode and open-ended streaming with `dlt.sources.incremental(lag=0)`
  - [x] Full refresh mechanism: resets local pipeline state via `pipeline.drop()`, cleans up DuckDB staging/raw schemas, and recreates tables natively via `dlt` to avoid DuckDB's `ALTER TABLE ADD COLUMN` constraint limitations
  - [x] Automatically refreshes downstream ODS and Marts views upon pipeline completion
