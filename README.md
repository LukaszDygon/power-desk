# Power Desk ⚡

An analyst dashboard for power and energy data, on a local dlt → DuckDB → dbt warehouse
orchestrated by Dagster.

- [Architecture](docs/architecture.md): layers, dimensions, load-id contract, data quality, catalogue
- [Ingestion study](docs/ingestion-study.md): how to store versioned publisher data with dlt, measured
- [ADR 0001](docs/adr/0001-keep-dlt-defaults-for-ingestion.md): keep dlt's default row handling; the measured avenues for later
- [Agent skills](#agent-skills): onboard a source or dataset, add a dashboard widget
- [Services](services/README.md): long-running receivers of push feeds (Elexon IRIS, ENTSO-E subscriptions), on Kubernetes
- [Logging and provenance](docs/logging.md): the log standard, and tracing a row through logs, dlt metadata and dbt artifacts
- [Platform](platform/README.md): the local cluster's log aggregation (Grafana) and catalogue (OpenMetadata)

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
.agents/skills/                 agent skills; .claude/skills links here
tools/                          one-off build scripts (the dashboard's bidding-zone map)
services/                       long-running services (own package, image, Helm chart, minikube dev setup)
libs/logging/                   the log standard (docs/logging.md), shared by the orchestrator and the services
integrations/openmetadata-duckdb/  OpenMetadata connector for the DuckDB warehouse (own project and lock)
platform/                       local cluster: Loki + Alloy + Grafana (logs), OpenMetadata (catalogue)
```

## Commands

```bash
uv run power-desk-dagster                        # orchestrator, http://localhost:3000
uv run power-desk                                # dashboard, http://localhost:8888
uv run power-desk-load-seed                      # seed week -> every pipeline -> dbt (dev only)
uv run power-desk-backfill [--sources <source>] [--start-date <d> --end-date <d> --chunk-days 31]
uv run power-desk-service <iris|entsoe-subscription>   # a service in the foreground (services/README.md)
make -C services dev                             # services on a local minikube cluster
make -C platform observability openmetadata      # Grafana (logs) and OpenMetadata on it (platform/README.md)

uv run dbt build --project-dir transform --profiles-dir transform
uv run python -m power_desk.catalog.refresh      # refresh official definitions (network)
uv run python -m power_desk.catalog.generate     # regenerate dbt sources and doc blocks
uv run python -m power_desk.catalog.describe [relation]
uv run dbt docs generate --project-dir transform --profiles-dir transform
uv run dbt docs serve --project-dir transform --profiles-dir transform --target-path transform/target

uv run pytest
uv run pyright                                     # type check src and tests
```

## Agent skills

Step-by-step procedures for coding agents, one `SKILL.md` each in `.agents/skills/`. `.claude/skills` is a
link to that folder, so Claude Code loads the same files (`/onboard-source`, `/create-widget`, or picked by
description). Edit them in `.agents/skills/` only.

- [`onboard-source`](.agents/skills/onboard-source/SKILL.md): a new publisher or dataset through every
  stage, from the dlt source to marts, with a check per stage
- [`create-widget`](.agents/skills/create-widget/SKILL.md): a dashboard card from a query over marts or
  entities

## Settings

Environment variables are listed in `src/power_desk/settings.py`; source credentials go in `.env`
(see `.env.example`).

