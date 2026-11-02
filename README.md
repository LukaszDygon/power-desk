# Power Desk ⚡

An analyst dashboard for power and energy data, on a local dlt → DuckDB → dbt warehouse
orchestrated by Dagster.

- [Architecture](docs/architecture.md): layers, dimensions, load-id contract, data quality, catalogue
- [Ingestion study](docs/ingestion-study.md): how to store versioned publisher data with dlt, measured
- [ADR 0001](docs/adr/0001-keep-dlt-defaults-for-ingestion.md): keep dlt's default row handling; the measured avenues for later
- [Data sources](docs/data-sources.md): European power, gas, carbon and weather publishers, forecast services and main global sources: data, zones, delivery, access
- [Agent skills](#agent-skills): onboard a source or dataset, add a dashboard widget
- [Services](services/README.md): long-running receivers of push feeds (Elexon IRIS, ENTSO-E subscriptions), on Kubernetes
- [Logging and provenance](docs/logging.md): the log standard, and tracing a row through logs, dlt metadata and dbt artifacts
- [Infra](infra/README.md): the local cluster, the services' deployment, log aggregation (Grafana) and catalogue (OpenMetadata)

## Layout

One directory per concern; each Python project has its own `pyproject.toml`, tests and type-check settings
in one uv workspace. Projects never import one another (import contracts in `pyproject.toml`): they
meet through `libs/` and the warehouse's files (DuckDB, the dbt manifest, the landing zone).

```
elt/                 publisher data into the warehouse (power_desk_elt)
  src/…/ingest/        dlt sources (sources/), their registry and pipelines; seed replay (seed/)
  src/…/transform/     dbt invocations and pending dlt loads
  src/…/orchestration/ Dagster assets, ingest jobs (jobs.py), schedules, sensors, checks
  src/…/catalog/       definitions, provider snapshots, dbt sources and docs generator
  src/…/cli/           command-line entry points
  dbt/                 dbt project: staging, ods, dims, marts, dlt_meta; seeds (dims, mappings)
  seed/                recorded publisher payloads for the seed week
  tests/               unit/: logic in isolation; integration/: pipelines, dbt and jobs on the seed
  bench/               ingestion experiments (docs/ingestion-study.md)
  .dagster/<env>/      Dagster instance configuration
dashboard/           read-only analyst dashboard (power_desk_dashboard)
  src/…                FastAPI app, queries, lineage, widget registry
  frontend/            the browser side: static assets (JS, CSS, map) and the page template
  tools/               one-off build scripts (the bidding-zone map)
  tests/               unit/; integration/: the API over the seed week, built by the ELT
services/            long-running receivers of push feeds (power_desk_services): code, tests, image
libs/logging/        the log standard (docs/logging.md), shared by the ELT and the services
libs/warehouse/      the warehouse contract: environment, file locations, connections (ELT and dashboard)
infra/               local cluster, the services' Helm chart, Grafana, OpenMetadata and its DuckDB connector
docs/                architecture, ADRs, studies, data sources
data/                runtime: warehouses, landing zone, logs; widgets.json (the dashboard's registry)
.agents/skills/      agent skills; .claude/skills links here
```

## Getting started

Needs [uv](https://docs.astral.sh/uv/) (it fetches Python 3.13); Docker, minikube and Helm only for `infra/`.

```bash
uv sync                          # every project into one environment (.venv)
make hooks                       # `make check` before every push to main
uv run power-desk-load-seed      # dev warehouse from the recorded seed week, offline
uv run power-desk                # the dashboard on it, http://localhost:8888
uv run power-desk-dagster        # the orchestrator, http://localhost:3000
```

Live data needs publisher credentials: copy `.env.example` to `.env` and fill it in.

## Commands

```bash
uv sync                                          # every project into one environment
uv run power-desk-dagster                        # orchestrator, http://localhost:3000
uv run power-desk                                # dashboard, http://localhost:8888
uv run power-desk-load-seed                      # seed week -> every pipeline -> dbt (dev only)
uv run power-desk-backfill [--sources <source>] [--start-date <d> --end-date <d> --chunk-days 31]
uv run power-desk-service <iris|entsoe-subscription>   # a service in the foreground (services/README.md)
make -C infra/services dev                       # services on a local minikube cluster
make -C infra observability openmetadata         # Grafana (logs) and OpenMetadata on it (infra/README.md)

uv run dbt build --project-dir elt/dbt --profiles-dir elt/dbt
uv run python -m power_desk_elt.catalog.refresh  # refresh official definitions (network)
uv run python -m power_desk_elt.catalog.generate # regenerate dbt sources and doc blocks
uv run python -m power_desk_elt.catalog.describe [relation]
uv run dbt docs generate --project-dir elt/dbt --profiles-dir elt/dbt
uv run dbt docs serve --project-dir elt/dbt --profiles-dir elt/dbt --target-path elt/dbt/target
```

## Before pushing

Run `make check` before pushing to main (`make hooks` once makes git do it on every push to main). It
lints the whole repository (ruff, and the import contracts between projects), then type-checks and tests
only the projects your branch changes since `origin/main`, committed or not, and their dependents
(`scripts/affected-projects`):

| Changed | Checked |
|---|---|
| `libs/logging/` | logging, elt, services |
| `libs/warehouse/` | warehouse, elt, dashboard |
| `elt/` (not `bench/`) | elt, dashboard (its tests query the marts the ELT builds) |
| `dashboard/`, `services/`, `infra/openmetadata-duckdb/` | that project (`connector` for the last) |
| `pyproject.toml`, `uv.lock`, `Makefile`, `scripts/` | every Python project |
| `docs/`, `infra/` otherwise | lint only |

`make -j check` runs the projects in parallel. The integration tests (ELT and dashboard) build the seed
week through dlt and dbt and take a few minutes; while iterating, run one project's checks
(`make check-elt`) or its unit tests (`uv run pytest elt/tests/unit`). `make check-all` runs everything;
`uv run pyright` type-checks every project in one pass. Tests run per project (each has its own `tests`
package), so a bare `pytest` at the root stops with these commands.
The pre-push hook checks the working tree, so commit or stash unrelated changes first; `git push
--no-verify` skips it.

## Agent skills

Step-by-step procedures for coding agents, one `SKILL.md` each in `.agents/skills/`. `.claude/skills` is a
link to that folder, so Claude Code loads the same files (`/onboard-source`, `/create-widget`, or picked by
description). Edit them in `.agents/skills/` only.

- [`onboard-source`](.agents/skills/onboard-source/SKILL.md): a new publisher or dataset through every
  stage, from the dlt source to marts, with a check per stage
- [`create-widget`](.agents/skills/create-widget/SKILL.md): a dashboard card from a query over marts or
  entities

## Settings

Environment variables are listed in `libs/warehouse/src/power_desk_warehouse/settings.py` (the warehouse's)
and `elt/src/power_desk_elt/settings.py` (the ELT's); source credentials go in `.env` (see `.env.example`).

