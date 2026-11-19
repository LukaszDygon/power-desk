# Architecture

How publisher data becomes queryable: dlt loads it into DuckDB, dbt conforms and documents it, Dagster schedules both.

```
publisher ─dlt─> raw ─> staging/<source> ─> ods (entities) ─> marts (hourly)
                                              │
                         dims (conformed dimensions, bridges, mappings)
```

## Principles

- **One place per step:** dlt extracts and loads, dbt transforms (one macro per kind), Dagster schedules.
- **Raw as published, versioned:** rows as sent, normalized only by dlt, every version kept (`scd2`).
- **Read by reference:** a resource fetches only its own data; other sources it reads from the warehouse.
- **Derived, never invented:** a missing value is null; an aggregate states its `coverage`.
- **One way to run each step:** a library function; only the orchestrator records runs and schedules.
- **Projects meet through files:** `elt`, `dashboard` and `services` share only `libs/` and the warehouse.
- **Departures:** listed once, in [deviations](deviations.md).

## Layers

| Layer | Holds | Rule |
|---|---|---|
| `raw` | a dlt table per resource | as published, every version, never edited |
| `staging/<source>` | a model per raw table | types, UTC, names, current version |
| `ods` | an incremental table per entity | every source, native resolution, conformed keys and units |
| `dims` | tables and seeds | dimensions, bridges, code mappings |
| `marts` | an incremental table per time-series entity | the entity on an hourly spine, one macro |
| `dlt_meta` | views, an audit table | which load each tracked model processed |

| Object | Name |
|---|---|
| raw table, staging model | `<source>__<dataset>`, `stg_<source>__<dataset>` |
| entity, mart | `ods_<entity>`, `mart_<entity>` |
| dimension, bridge, mapping | `dim_<name>`, `bridge_<name>_hierarchy`, `map_<dimension>` |

- **Columns:** time, dimension keys, measures, provenance, in that order; one measure name across actuals and forecasts.
- **Marts:** one row per series and hour holding data, aggregated as `dim_metric` says, newest publication wins.
- **Marts are uniform, not analyses:** an entity need not have one; areas stay at every published level.
- **Dimensions:** a query needs only values, a datetime and a few shared natural keys; bridges roll up in one join.
- **Traceability:** entity rows keep `source_dataset`, source code and `_dlt_load_id`.

## Ingestion

- **Contract:** a `@dlt.source(window)` plus a `SourceSpec` per source, in `ingest/registry.py`.
- **Windows:** open-ended (from the cursor, at most `max_days`) or bounded backfills; fetch errors fail the run.
- **Dispositions:** `merge` + `scd2` everywhere, keyed per kind of source (Appendix B).
- **dlt's defaults:** dlt names, types and keys rows; its schemas define the dbt sources ([ADR 0001](adr/0001-keep-dlt-defaults-for-ingestion.md)).
- **Seed and push feeds:** recorded payloads stand in for publishers; services land push feeds ([services](../services/README.md)).

## Orchestration and quality

- **Jobs:** one per publication cadence, loading then building dbt over pending loads; catch-up while capped.
- **Backfills and nightly:** backfill jobs by calendar month; nightly tests everything and refreshes docs.
- **Load-id contract:** a load is pending for a model until `dlt_load_audit` records it, after the model and its tests pass.
- **Tests:** builds test pending loads, nightly every row; key failures block, gaps warn; failures in `test_failures`.
- **Freshness and writer:** two freshness checks per raw table; one pool for every DuckDB writer.

## Catalogue, logs, environments

- **Definitions:** each concept once, quoted from an official source; undocumented columns fail.
- **Contracts:** ODCS, exported from dbt, verified by its tests ([data contracts](data-contracts.md)).
- **Logs:** one format carrying dlt, dbt and Dagster ids ([logging and provenance](logging.md)).
- **Environments:** `POWER_DESK_ENV` (`dev`, `prod`); automation starts only in `prod`; credentials are dlt secrets.

## Appendix A: Evidence

- **dlt's defaults over alternatives:** measured in [the ingestion study](adr/evidence/0001-ingestion-study.md).

## Appendix B: Details

**Principles.** Data without structure is parsed by a data class (pydantic) that owns its parser; a generic parser may serve several classes. Data without structure means e.g. an HTML
page or a binary grid. Orchestration details are runs, schedules and materializations; steps don't know who
calls them.

**Layers.** Staging also adds the source's derived fields; it is views, with incremental tables for large
sources. An ods build replaces the partitions pending loads touch. A curated dimension is its seed.

**Columns.** Time (`timestamp_utc`; `interval_minutes` in entities), dimension keys (`*_eic_code`,
`technology_code`, `time_horizon`), measures (`<quantity>_mw`; `coverage` in marts), provenance
(`source_dataset`, `source_code`, `_dlt_load_id`). Entity examples: `generation_actual`, `demand_forecast`.

**Marts.** Every mart is `hourly_series` over its entity. Steps are the shared macros of `macros/time/`: where a period ends, splitting a period across the
hours it overlaps, aggregating a series' rows within an hour. Rates, levels and prices: time-weighted mean
over the covered minutes. UTC periods: a day or month published from local midnight ends where the series'
next period starts, so it lasts 23 or 25 hours at clock changes.

**Dimensions.** Each is keyed by a natural key (an EIC or canonical code) and versioned where its publisher
revises it. Conformed dimensions: area, border, technology, time horizon, resource, party, site, source dataset, metric. Mappings translate publisher codes to dimension keys, at the most specific level the publisher supports. Bridge examples: unit → plant, zone → member state, technology → group. Mappings live in
`seeds/mappings`.

**Ingestion.** Modules live in `ingest/sources/`. A source names the relations it reads by reference
(`SourceSpec.references`); they are built before it loads, and its raw assets depend on them. Recorded
payloads are in `elt/seed/` and run through the real pipelines. Load files are Parquet; dlt schemas are
exported to `ingest/schemas/`. Services acknowledge a batch once it has landed.

| Kind | Cursor | Disposition |
|---|---|---|
| Stream | the value's time, or the publication time where the publisher revises | `merge` + `scd2` on the natural key |
| Event messages | the publication time | `merge` + `scd2` on the message id |
| Snapshot | none: the whole file, skipped while unchanged | `merge` + `scd2`, full extract |
| File partitions | the publication time | `merge` + `scd2` on the natural key |
| Forecast runs | the run | `merge` + `scd2` on the natural key |

**Orchestration.** Jobs are in `orchestration/jobs.py`; every raw table is in exactly one job, and each job
has a schedule. Backfill jobs are `backfill_<source>`; Dagster splits a range into runs and tracks them.
Freshness checks run against the table's catalogue preset: `recently_fetched` (newest load) and
`recent_data` (newest data by its own datetime). Ingestion time comes only from dlt's load metadata.

**Load ids.** One macro defines pending loads (`macros/dlt/loads.sql`). Tracked models rebuild only the
partitions pending loads touch, and are idempotent on their grain.

**Data quality.** Tests read pending rows (`dlt_scope: recent`) or every row (`all`, nightly); which tests
run is dbt's selection. A raw table before its first load reads as empty. Uniqueness guards check touched
keys against the whole table.

| Check | Layer | On failure |
|---|---|---|
| Natural-key and row-version uniqueness | raw | blocks |
| Key uniqueness, ranges, completeness | staging | blocks; completeness warns when scoped, errors nightly |
| Entity-key uniqueness, dimension keys resolve | ods | blocks; unmapped codes warn |
| Mapping keys exist in their dimension | dims | blocks |
| Grain uniqueness, ranges | marts | blocks |

**Catalogue.** Definitions are `catalog/definitions/*.yml`; citations are `provider:kind/id` (fetched into
`catalog/snapshots/`) or a document link. `catalog.generate` writes a dbt doc block per definition and the
dbt sources; generation fails on undocumented raw columns, tests on undocumented warehouse columns.
`catalog.contracts` exports an ODCS contract per mart, entity and dimension.
