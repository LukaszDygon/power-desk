# Architecture

dlt loads each publisher's data into DuckDB, dbt conforms and documents it, and Dagster schedules both.

```
publisher ─dlt─> raw ─> staging/<source> ─> ods (entities) ─> marts (hourly)
                                              │
                         dims (conformed dimensions, bridges, mappings)
```

## Principles

- **One place per step.** Extraction and loading in dlt sources, every transformation in dbt, scheduling
  in Dagster. Each kind of transformation is one macro, reused wherever it applies.
- **Raw as published.** Ingestion yields rows as the publisher sends them, normalized only by dlt. Data
  without structure (an HTML page, a binary grid) is parsed by a data class (pydantic) that owns its parser;
  a generic parser may serve several classes. A resource fetches only its own data; data it needs from
  another source it reads by reference from the warehouse.
- **Versioned raw.** `raw` keeps every version (`scd2`), so the data reads as it was at any time.
- **Derived, never invented.** A value the publisher does not give is null; an aggregate states how much of
  its period holds data (`coverage`).
- **One way to run each step.** A library function, called directly or by the orchestrator. Only the
  orchestrator records orchestration details (runs, schedules, materializations); the steps don't know who
  calls them.
- **Projects meet through files.** `elt`, `dashboard` and `services` never import one another; they share
  `libs/` and the warehouse's files.

A departure from these is an exception, recorded once in [deviations](deviations.md).

## Layers

| Layer | Content | Rules |
|---|---|---|
| `raw` | dlt tables, one per resource | As published, keyed by the natural key, every version kept. Never edited. |
| `staging/<source>` | one model per raw table | Types, UTC time, names, the current version, the source's derived fields. Views; incremental tables for large sources. |
| `ods` | incremental tables, one per entity | Every source providing the entity, at its published interval and resolution, conformed to units and dimension keys. A build replaces the partitions pending loads touch. |
| `dims` | tables and seeds | Conformed dimensions, hierarchy bridges, mappings from publisher codes. A curated dimension is its seed. |
| `marts` | incremental tables, one per time-series entity | The entity on an hourly spine, through one macro. |
| `dlt_meta` | views and an audit table | Which dlt load each tracked model processed. |

`marts` is a uniform, documented layer that analytical queries build on, not a layer of analyses. An
entity need not have a mart.

## Naming

| Object | Name |
|---|---|
| raw table (dlt resource) | `<source>__<dataset>` |
| staging model | `stg_<source>__<dataset>` |
| entity | `ods_<entity>` (e.g. `generation_actual`, `demand_forecast`) |
| mart | `mart_<entity>` |
| dimension, bridge, mapping | `dim_<name>`, `bridge_<name>_hierarchy`, `map_<dimension>` |

Entity and mart columns come in a fixed order: time (`timestamp_utc`; `interval_minutes` in entities),
dimension keys (`*_eic_code`, `technology_code`, `time_horizon`), measures (`<quantity>_mw`; `coverage` in
marts), then provenance (`source_dataset`, `source_code`, `_dlt_load_id`). A measure keeps one name across
actual and forecast entities.

## Marts

Every mart is `hourly_series` over its entity: one row per series (the dimension keys) and hour holding
data. Its steps are the shared macros of `macros/time/`: where a period ends, splitting a period across
the hours it overlaps, and aggregating a series' rows within an hour.

- **Measures** aggregate as `dim_metric` says, the one definition: rates, levels and prices are the
  time-weighted mean over the covered minutes; volumes are pro-rated into the hour.
- **Precedence:** where a series' periods overlap, the most recently published row prevails.
- **UTC periods:** a day or month published from local midnight ends where the series' next period starts,
  so it lasts 23 or 25 hours at clock changes.
- **Areas** stay at every level the publisher uses; choosing a level before summing is the query's business.

## Dimensions

A query needs only values, a datetime and the natural keys of a small set of shared dimensions; the
dimensions explain each key and how keys relate.

- **Conformed dimensions:** area, border, technology, time horizon, resource, party, site, source dataset
  and metric, each keyed by a natural key (an EIC or canonical code) and versioned where its publisher
  revises it.
- **Bridges** relate keys across granularities (unit → plant, zone → member state, technology → group), so
  a roll-up to any level is one join.
- **Mappings** (`seeds/mappings`) translate each publisher's codes into dimension keys, at the most
  specific level the publisher supports.
- **Traceability:** an entity row keeps its `source_dataset`, source code and `_dlt_load_id`, which lead
  back to the raw row and its load.

## Ingestion

Each module in `ingest/sources/` exposes a `@dlt.source(window)` and a `SourceSpec`, registered in
`ingest/registry.py`. The window is open-ended (resume from the cursor, at most `max_days` new days) or
bounded (a backfill, which leaves the cursor untouched). A source names the warehouse relations it reads by
reference (`SourceSpec.references`); they are built before it loads. Fetch errors fail the run, so no gap is
skipped. Recorded payloads (`elt/seed/`) replace the publishers in dev and tests, through the real pipelines.

| Kind | Cursor | Disposition |
|---|---|---|
| Stream | the value's time, or the publication time where the publisher revises | `merge` + `scd2` on the natural key |
| Event messages | the publication time | `merge` + `scd2` on the message id |
| Snapshot | none: the whole file, skipped while unchanged | `merge` + `scd2`, full extract |
| File partitions | the publication time | `merge` + `scd2` on the natural key |
| Forecast runs | the run | `merge` + `scd2` on the natural key |

dlt names, types and keys every row (Parquet load files); its schemas are exported to `ingest/schemas/` and
define the dbt sources. Why we keep dlt's defaults, and when to revisit:
[ADR 0001](adr/0001-keep-dlt-defaults-for-ingestion.md).

Push feeds are received by long-running services (`services/`), which land each batch as a dlt load in a
landing zone and acknowledge it once landed ([services](../services/README.md)).

## Orchestration

- **Ingest jobs** (`orchestration/jobs.py`) group raw tables by publication cadence; every raw table is in
  exactly one. Each job loads its tables, then builds every dbt model over the pending loads; it has a
  schedule and a catch-up run while its last run was capped.
- **Backfill jobs** (`backfill_<source>`) run the same assets over bounded windows, one calendar month per
  partition; Dagster splits a range into runs and tracks them.
- **Nightly** tests the whole warehouse and refreshes the dbt docs.
- **Dependencies:** a source's raw assets depend on the relations it reads by reference.
- **Freshness:** two checks per raw table against its catalogue preset: the newest load
  (`recently_fetched`) and the newest data by its own datetime (`recent_data`). Ingestion time comes only
  from dlt's load metadata.
- **One writer:** DuckDB admits one, so every asset that writes it shares a pool.

## Load-id contract

1. A completed dlt load is pending for a tracked model until `dlt_meta.dlt_load_audit` records it for that
   model. One macro defines it (`macros/dlt/loads.sql`).
2. Tracked models rebuild the partitions pending loads touch; they are idempotent on their grain.
3. A load is recorded for a model once the model and its tests pass.

## Data quality

Tests read the rows of pending loads (`dlt_scope: recent`) or every row (`all`, nightly); which tests run is
dbt's selection. A raw table before its first load reads as empty. Uniqueness guards check touched keys
against the whole table.

| Check | Layer | On failure |
|---|---|---|
| Natural-key and row-version uniqueness | raw | blocks |
| Key uniqueness, ranges, completeness | staging | blocks; completeness warns when scoped, errors nightly |
| Entity-key uniqueness, dimension keys resolve | ods | blocks; unmapped codes warn |
| Mapping keys exist in their dimension | dims | blocks |
| Grain uniqueness, ranges | marts | blocks |

Failing rows are stored in `test_failures.<test>`.

## Catalogue

- **Definitions:** `catalog/definitions/*.yml` define each table and column concept once, quoted from and
  citing an official source (`provider:kind/id`, fetched into `catalog/snapshots/`, or a document link).
- **Generation:** `catalog.generate` writes a dbt doc block per definition and the dbt sources; generation
  fails on undocumented raw columns, and tests fail on undocumented warehouse columns.
- **Data contracts:** `catalog.contracts` exports an ODCS contract per mart, entity and dimension from the
  dbt project; dbt tests verify them ([data contracts](data-contracts.md)).

## Logging and environments

Every process logs one record format, carrying the identifiers dlt, dbt and Dagster issue
([logging and provenance](logging.md)). `POWER_DESK_ENV` (`dev`, `prod`) selects the warehouse file, dbt
target, dlt state and Dagster instance; automation starts on its own only in `prod`. Credentials are dlt
secrets, read from the environment or `.env`.
