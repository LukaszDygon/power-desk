# Power Desk ⚡

A high-density minimalist analyst dashboard for UK Power & Energy Data.

## Features
- **ELT Pipeline (`dlt`):** Elexon BMRS source builder with raw data preservation and incremental merge on natural keys.
- **DBT-style Modeling:** DuckDB SQL Views for ODS and Marts with settlement period to UTC natural key resolution.
- **Analyst Terminal Grid:** Draggable, resizable cards powered by GridStack.js.
- **Open-Source Lineage:** DAG visualization via Cytoscape.js and Dagre.
- **Functional Energy Palette:** Meaningful colors for generation fuels (Wind, Solar, Nuclear, CCGT, Demand, Forecast).
- **Agent Widget Skill:** Extensible `.agents/skills/create-widget/SKILL.md` allowing AI agents to generate and mount new analytical cards.

## Commands & Workflow

Data ingestion and server execution are completely decoupled:

### 1. Run Web Dashboard (Read-Only Server)
```bash
uv run uvicorn power_desk.app:app --port 8888 --reload
```
*The server purely handles queries and UI rendering with zero data-loading side effects.*

### 2. Load Seed Data (Independent Task)
```bash
uv run python scripts/load_seed.py
```
*Loads the curated 7-day realistic power datasets into DuckDB via `dlt` and registers SQL views.*
*Optionally pass `--generate` to re-synthesize the parquet files.*

### 3. Incremental Backfill (Independent Task)
```bash
# Incremental stream until data ends (lag=0)
uv run python scripts/backfill.py --start-date 2024-03-01

# Full refresh / schema rebuild
uv run python scripts/backfill.py --refresh drop_sources --start-date 2024-03-01 --end-date 2024-03-07
```

### 4. Run Test Suite
```bash
uv run pytest
```
