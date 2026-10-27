# Power Desk ⚡

An analyst dashboard for power and energy data, on a local dlt → DuckDB → dbt warehouse
orchestrated by Dagster.

- [Architecture](docs/architecture.md): layers, dimensions, load-id contract, data quality, catalogue
- [Add a data source](.agents/skills/add-source/SKILL.md) · [Add a dashboard widget](.agents/skills/create-widget/SKILL.md)

## Layout

```
src/power_desk/settings.py      environment and file locations
src/power_desk/ingest/          dlt sources (sources/), their registry and pipelines; seed replay (seed/)
src/power_desk/transform/       dbt invocations and pending dlt loads
src/power_desk/orchestration/   Dagster assets, ingest jobs (jobs.py), schedules, sensors, checks
src/power_desk/catalog/         definitions, provider snapshots, dbt sources and docs generator
src/power_desk/dashboard/       read-only dashboard and widget registry
src/power_desk/cli/             command-line entry points
transform/                      dbt project: staging, ods, dims, marts, dlt_meta; seeds (dims, mappings)
data/seed/                      recorded publisher payloads for the seed week
tests/unit, tests/integration   logic in isolation; pipelines, dbt, jobs and API on the seed
```

## Commands

```bash
uv run power-desk-dagster                        # orchestrator, http://localhost:3000
uv run power-desk                                # dashboard, http://localhost:8888
uv run power-desk-load-seed                      # seed week -> every pipeline -> dbt (dev only)
uv run power-desk-backfill [--sources <source>] [--start-date <d> --end-date <d> --chunk-days 31]

uv run dbt build --project-dir transform --profiles-dir transform
uv run python -m power_desk.catalog.refresh      # refresh official definitions (network)
uv run python -m power_desk.catalog.generate     # regenerate dbt sources and doc blocks
uv run python -m power_desk.catalog.describe [relation]
uv run dbt docs generate --project-dir transform --profiles-dir transform
uv run dbt docs serve --project-dir transform --profiles-dir transform --target-path transform/target

uv run pytest
```

## Settings

Environment variables are listed in `src/power_desk/settings.py`; source credentials go in `.env`
(see `.env.example`).

