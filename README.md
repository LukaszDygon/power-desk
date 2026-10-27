# Power Desk ⚡

An analyst dashboard for power and energy data, on a local dlt → DuckDB → dbt warehouse
orchestrated by Dagster.

- [Architecture](docs/architecture.md): layers, dimensions, load-id contract, data quality, catalogue
- [Add a data source](.agents/skills/add-source/SKILL.md) · [Add a dashboard widget](.agents/skills/create-widget/SKILL.md)

## Layout

```
src/power_desk/ingest/          dlt sources and their registry (pipelines.py); exported dlt schemas
src/power_desk/orchestration/   Dagster assets; ingest jobs and schedules (jobs.py)
src/power_desk/catalog/         definitions, provider snapshots, dbt sources/docs generator
transform/                      dbt project: staging, ods, dims, marts, dlt_meta; seeds (dims, mappings)
src/power_desk/app.py           read-only dashboard
```

## Commands

```bash
uv run python scripts/dagster.py                 # orchestrator, http://localhost:3000
uv run uvicorn power_desk.app:app --port 8888    # dashboard
uv run python scripts/load_seed.py               # sample data -> dlt -> dbt (dev only)
uv run python scripts/backfill.py [--pipelines <source>] [--start-date <d> --end-date <d> --chunk-days 31]

uv run dbt build --project-dir transform --profiles-dir transform
uv run python -m power_desk.catalog.refresh      # refresh official definitions (network)
uv run python -m power_desk.catalog.generate     # regenerate dbt sources and doc blocks
uv run python -m power_desk.catalog.describe [relation]
uv run dbt docs generate --project-dir transform --profiles-dir transform
uv run dbt docs serve --project-dir transform --profiles-dir transform --target-path transform/target

uv run pytest
```

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `POWER_DESK_ENV` | `dev` | `dev` or `prod`: warehouse `data/warehouse_<env>.duckdb`, dbt target, dlt state, Dagster instance `.dagster/<env>` |
| `POWER_DESK_DUCKDB_PATH` | | explicit warehouse file |
| `POWER_DESK_START_DATE` | `2024-01-01` | first date the warehouse must cover (completeness) |

One-off data migrations live in `scripts/migrations/`.
