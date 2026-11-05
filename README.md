# Power Desk ⚡

An analyst dashboard for power and energy data, on a local dlt → DuckDB → dbt warehouse
orchestrated by Dagster.

- [Architecture](docs/architecture.md): layers, keys, the load-id contract, data quality, the catalogue
- [Deviations](docs/deviations.md): every place the code departs from the architecture, and why
- [Decisions](docs/adr/): one record per decision, with its evidence
- [Data contracts](docs/data-contracts.md): an ODCS contract per mart, entity and dimension
- [Onboarding a dataset](docs/onboarding.md): from a request to an accepted pipeline
- [Data sources](docs/data-sources.md): the publishers, their data and access
- [Logging and provenance](docs/logging.md): the log standard, and tracing a row
- [Services](services/README.md) and [infra](infra/README.md): push-feed receivers, the cluster, Grafana, OpenMetadata
- [Agent instructions](AGENTS.md) and their skills (`.agents/skills/`)

## Layout

One directory per concern; each Python project has its own `pyproject.toml`, tests and type-check settings
in one uv workspace. Projects never import one another (import contracts in `pyproject.toml`): they
meet through `libs/` and the warehouse's files (DuckDB, the dbt manifest, the landing zone).

```
elt/                 publisher data into the warehouse (power_desk_elt)
  src/…/ingest/        dlt sources (sources/), their registry and pipelines; seed replay (seed/)
  src/…/transform/     dbt invocations
  src/…/orchestration/ Dagster assets, jobs (jobs.py), schedules, sensors, checks
  src/…/catalog/       definitions, provider snapshots, dbt sources and docs generator
  src/…/cli/           command-line entry points
  src/…/onboarding/    profiling samples and acceptance runs of a new source
  dbt/                 dbt project: staging, ods, dims, marts, dlt_meta; seeds (dims, mappings)
  contracts/           data contracts (generated)
  seed/                recorded publisher payloads for the seed week
  tests/               unit/: logic in isolation; integration/: pipelines, dbt and jobs on the seed
  .dagster/<env>/      Dagster instance configuration
dashboard/           read-only analyst dashboard (power_desk_dashboard): app, widget registry, frontend
services/            long-running receivers of push feeds (power_desk_services)
libs/logging/        the log standard, shared by the ELT and the services
libs/warehouse/      the warehouse contract: environment, file locations, connections
infra/               local cluster, the services' Helm chart, Grafana, OpenMetadata and its DuckDB connector
docs/                architecture, deviations, ADRs, data sources
data/                runtime (gitignored): warehouses, landing zone, logs, onboarding artefacts
```

## Commands

Needs [uv](https://docs.astral.sh/uv/) (it fetches Python 3.13); Docker, minikube and Helm only for `infra/`.
Live data needs publisher credentials: copy `.env.example` to `.env` and fill it in.

```bash
uv sync                                          # every project into one environment (.venv)
make hooks                                       # `make check` before every push to main
uv run power-desk-load-seed [--fresh]            # dev warehouse from the recorded seed week, offline
uv run power-desk                                # dashboard, http://localhost:8888
uv run power-desk-dagster                        # orchestrator, http://localhost:3000
uv run power-desk-service <iris|entsoe-subscription>   # a service in the foreground
uv run power-desk-profile <source>__<dataset> <files> [--key ...] [--time ...]   # profile publisher samples
uv run power-desk-accept <source> --start-date <d> --end-date <d>               # acceptance run of a source
make -C infra/services dev                       # services on a local minikube cluster
make -C infra observability openmetadata         # Grafana and OpenMetadata on it

uv run dbt build --project-dir elt/dbt --profiles-dir elt/dbt
uv run python -m power_desk_elt.catalog.refresh  # refresh official definitions (network)
uv run python -m power_desk_elt.catalog.generate # regenerate dbt sources and doc blocks
uv run python -m power_desk_elt.catalog.describe [relation]
uv run python -m power_desk_elt.catalog.contracts [--check]   # regenerate data contracts (after a dbt build)
```

A backfill is the Dagster job `backfill_<source>`: select the months in its Partitions tab and launch; each
month is a run. Scheduled jobs then keep the source current.

## Checks

`make check` lints the repository (ruff, the import contracts, unique ADR numbers), then type-checks and
tests what the branch changes since `origin/main`, with its dependents (`scripts/affected-projects` decides).
`make check-all` runs everything; `make check-<project> TESTS_<project>=<paths>` one project. A pass on a
clean tree is recorded, and the pre-push hook (`make hooks`) skips a tree that already passed; it fails at
once when `origin/main` has moved. Tests run per project, each with its own `tests` package.

## Settings

Environment variables are listed in `libs/warehouse/src/power_desk_warehouse/settings.py` (the warehouse's)
and `elt/src/power_desk_elt/settings.py` (the ELT's); source credentials go in `.env` (see `.env.example`).
