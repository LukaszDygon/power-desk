# Architecture

dlt loads each publisher's data into DuckDB, dbt conforms and documents it, and Dagster
schedules both.

```
publisher ─dlt─> raw ─> staging/<source> ─> ods (entities) ─> marts
                                              │
                         dims (conformed dimensions, bridges, mappings)
```

## Layers

| Layer | Content | Rules |
|---|---|---|
| `raw` | dlt tables, one per resource | As published, keyed by the natural key: replaced (streams) or versioned (scd2: snapshots, file partitions). Never edited. |
| `staging/<source>` | views, one per raw table | Types, UTC time, names, source-specific dedup, shared column vocabulary. File partitions: incremental tables of the current versions, by natural key. |
| `ods` | incremental tables, one per entity | Union of every source providing the entity at its published intervals (every resolution published), conformed to units and dimension keys. A build replaces the (area, hour) partitions pending loads touch, transforming only those. |
| `dims` | tables + seeds | Conformed dimensions, hierarchy bridges, and mappings from publisher codes. |
| `marts` | incremental tables | Built on `ods` + `dims`; rebuild only grains touched by pending loads. |
| `marts/combined` | incremental tables, one per entity | Every source and area on an hourly spine: one row per series and hour, values, `coverage`, dimension keys, provenance. |
| `dlt_meta` | views + audit table | Which dlt load each mart processed, in which dbt / Dagster run. |

`staging`, `ods`, `dims` and `marts` may be revised as new data arrives; `raw` stays true to
the source.

## Naming

| Object | Name |
|---|---|
| raw table (dlt resource) | `<source>__<dataset>` |
| staging model | `stg_<source>__<dataset>` |
| entity | `ods_<entity>` (e.g. `generation_actual`, `demand_forecast`) |
| combined mart | `mart_<entity>`, the same entity across sources and areas, hourly |
| business mart | `mart_<scope>_<subject>` (e.g. `mart_gb_generation_mix`) |

Entity and mart columns come in a fixed order: time (`timestamp_utc`, `interval_minutes` in entities),
dimension keys (`*_eic_code`, `technology_code`, `time_horizon`), measures (`<quantity>_mw`; `coverage`
in hourly marts), then provenance (`source_dataset`, `source_code`, `_dlt_load_id`). A measure keeps one
name across actual and forecast entities.

### Hourly marts

Each combined mart puts its entity on an hourly spine (`hourly_series`): one row per series (the
dimension keys) and hour holding data, so every entity is queried by shared dimension keys and the
hour.

- **Precedence:** where a series' published periods overlap (a period republished at another
  resolution), the most recently published row prevails, 5 minutes at a time.
- **UTC periods:** every period is a UTC interval. Days and months published from local midnight
  last 23 or 25 hours at clock changes, so they end where the series' next period starts (when that is
  within an hour of the nominal length), not after a fixed 24 hours.
- **`coverage`:** the fraction of the hour (0.0-1.0) holding data from the source.
- **Aggregation** follows the measure (`dim_metric`): power, prices and capacities are the
  time-weighted mean over the covered minutes (times `coverage` for the mean with missing minutes as
  zero); volumes (MWh) are pro-rated into the hour and summed.
- **Areas** stay at every level the publisher uses (bidding zone, control area, country); choosing a
  level before summing areas is the query's business.

## Dimensions

**Goal:** a query needs only values, a datetime, and the natural keys of a small set of shared
dimensions; the dimension tables explain what each key means and how keys relate.

- **Mart rows** are `timestamp_utc` (the hour), dimension keys, measures, `coverage` and provenance
  (`source_dataset`, `_last_dlt_load_id`).
- **Conformed dimensions:** area, border, technology, time horizon, resource, party, source dataset,
  plus the metrics the marts carry (unit, hourly aggregation). Each is keyed
  by a natural key (EIC code or canonical code) and versioned where its publisher revises it.
- **Bridges** relate keys across granularities (unit → plant, zone → member state, technology →
  group). Rolling a row up to any level is one join. They are graphs, not trees.
- **Mappings** (`seeds/mappings`) translate each publisher's codes into dimension keys, at the most
  specific level the publisher supports. Incompatible schemes meet on the same concepts.
- **Traceability:** an ODS row keeps its `source_dataset`, source code and `_dlt_load_id`, which
  lead back to the raw row and the dlt load that delivered it.

## Ingestion

- **Contract:** each module in `ingest/sources/` exposes a `@dlt.source(window: RunWindow)` and a
  `SourceSpec`, registered in `ingest/registry.py` (`ingest/spec.py`). The window carries the start,
  the inclusive end of a bounded backfill and the per-run cap (`max_days`, default
  `SourceSpec.max_days_per_run`). Raw payloads are yielded untouched.
- **Seed:** recorded and synthetic payloads (`elt/seed/`) replace the publishers (`ingest/seed/`),
  so the dev warehouse and the integration tests run the real pipelines.
- **Streams** have one cursor per resource and fetch at most `max_days` new days from it.
  Bounded backfills leave the cursor untouched. Fetch errors fail the run, so no gap is skipped.
- **Revised streams** (NESO) are streams of rows the publisher revises in place: the cursor is the
  upload time, so a resubmission is new data, and they load as scd2 merged on the natural key, like
  file partitions. NESO at times appends a resubmission instead of replacing it, so the upload time
  joins the `primary_key` but not the `merge_key`; staging keeps the latest upload.
- **Snapshots** (reference files) re-read the whole file, skip it while unchanged (ETag / hash), and
  load with scd2, so changes and withdrawals keep their history.
- **File partitions** (periodic files the publisher re-exports when revised) load the files new or
  changed since their last load, at most `max_days` of periods per run, as scd2 merged on the natural
  key (`merge_key` = `primary_key`): a revision closes the row's previous version, and the same row may
  arrive in several files. A row missing from a re-export stays current. The cursor is the latest
  publication time (`UpdateTime`), since revisions and re-forecasts are new data. Where an export lists
  several documents per natural key (energy prices, `InstanceCode`), the document id joins the
  `primary_key` but not the `merge_key`, so a revision closes them all; staging keeps the latest update.

### Write dispositions

dlt names, types and keys every row; we add no columns and change no values before loading.
Measurements and alternatives (Arrow, DuckLake, Delta, Iceberg): [ingestion study](ingestion-study.md);
why we keep dlt's defaults and when to revisit: [ADR 0001](adr/0001-keep-dlt-defaults-for-ingestion.md).

| Kind | Disposition | `_dlt_id` | Why |
|---|---|---|---|
| Streams (Elexon, PVLive) | `merge` + `delete-insert` on `primary_key` | row id | one row per key, also when a load repeats it; a republication replaces it |
| Snapshots (EIC) | `merge` + `scd2` (full extract, no `merge_key`) | hash of the row (version) | every version kept; withdrawn codes are closed |
| File partitions (ENTSO-E) | `merge` + `scd2`, `merge_key` = `primary_key` | hash of the row (version) | every version kept; only keys in the load are closed |
| Revised streams (NESO) | `merge` + `scd2`, `merge_key` = natural key | hash of the row (version) | every submission kept; only keys in the load are closed |

- **Rows, not Arrow:** dlt computes the scd2 row hash only for row items (dicts); for Arrow tables it
  adds none and scd2 cannot run. ENTSO-E exports are streamed to disk, read by DuckDB (which infers
  their types) and yielded in batches with dlt's `fetch_json`, so memory stays at batch size.
- **Parquet load files** for every resource: dlt's DuckDB default (`insert_values`) is 30-50x slower
  to load. Measured on one ENTSO-E month (848k rows): about 25 s, of which dlt's per-row normalize is
  about 14 s; the merge itself adds 1-2 s.
- **Names:** dlt's `snake_case` keeps a trailing `x` for brackets (`DateTime(UTC)` -> `date_time_utcx`);
  staging renames.
- **dlt schemas** are exported to `ingest/schemas/` and define the dbt sources.

### Services (push feeds)

Feeds the publisher pushes (Elexon IRIS, ENTSO-E subscriptions) are received by long-running
services (`services/`, on Kubernetes). They never write the warehouse: each batch is a dlt load into
a landing zone (filesystem destination, appended as published), acknowledged to the publisher only
after it lands (at least once). The orchestrator loads the landing zone into `raw` like any other
source. Details: [services](../services/README.md).

## Orchestration

- **`orchestration/jobs.py`** groups raw tables by publication cadence; every raw table is in exactly
  one job. Each entry yields a job, a schedule and a catch-up branch.
- **Freshness** has two checks per raw table, both against its catalog `freshness` preset:
  `recently_fetched` (the newest dlt load, `_dlt_load_id`) shows ingestion is delivering;
  `recent_data` (the newest data by its own datetime, the dlt cursor) ignores re-delivered copies and
  backfills of old data. Ingestion time comes only from dlt's metadata.
- **Every ingest job builds all dbt models.** Staging reads raw tables through `dlt_source()`, which is
  empty until a table's first load, so entities build from the sources loaded so far; tests
  downstream of a never-loaded table are skipped.
- **The catch-up sensor** re-runs a job while its last run was capped.
- **Nightly** runs every test unscoped and refreshes dbt docs.
- **One run at a time:** DuckDB allows a single writer.

## Logging and provenance

Every process logs one record format (OpenTelemetry's log data model), and records about data carry the
identifiers dlt, dbt and Dagster already issue: `dlt.load_id`, `dbt.invocation_id`, `dagster.run_id`. Shared
code binds them (a dlt tracking hook, Dagster's run metadata), so call sites log plain messages; each dlt
load is a `dlt.load` event, and dbt stamps the Dagster run id into its artifacts. Details, and what
OpenMetadata reads from where: [logging and provenance](logging.md).

## Load-id contract

1. A completed dlt load (`raw._dlt_loads.status = 0`) is pending for a mart until
   `dlt_meta.dlt_load_audit` records it for that mart.
2. The orchestrator passes the pending ids to dbt (`--vars dlt_load_ids`). Without it, macros
   compute the same set.
3. Marts recompute touched grains, and tests read only pending rows. Uniqueness guards check
   touched keys against the whole table.
4. A load is recorded only when the mart and its tests pass. Reprocessing is safe: marts are
   idempotent on their grain.

## Data quality

| Check | Layer | On failure |
|---|---|---|
| Natural-key (per valid-to under scd2) / row-version uniqueness | raw | blocks |
| Key uniqueness, ranges, completeness | staging | blocks; completeness warns in scheduled runs, errors nightly |
| Entity-key uniqueness, dimension keys resolve | ods | blocks; unmapped codes warn |
| Mapping keys exist in their dimension | dims | blocks |
| Grain uniqueness, fan-out, business rules | marts | blocks; business rules may warn |

Failing rows are stored in `test_failures.<test>`.

## Catalogue

- **Definitions:** `catalog/definitions/*.yml` define each table and column concept once. They cite
  official sources as provider references (`provider:kind/id`, fetched into `catalog/snapshots/`) or
  as document links with section and page.
- **Descriptions and references:** doc blocks hold the definition only (the local description, else
  the publisher's wording); citations go to `meta.references` of the dbt sources.
- **Generation:** `catalog.generate` writes one dbt doc block per definition, plus the dbt sources.
  Models reference the blocks with `{{ doc() }}`.
- **Coverage:** generation fails on undocumented raw columns, and tests fail on undocumented
  warehouse columns.
- **Data contracts:** `catalog.contracts` exports an ODCS contract per mart, entity and dimension
  (`elt/contracts/`), from the descriptions, data tests and query guidance (`meta`) of the dbt project;
  dbt tests verify them. Details: [data contracts](data-contracts.md).

## Environments

`POWER_DESK_ENV` (`dev`, `prod`) selects the warehouse file, dbt target, dlt state and Dagster
instance. Automation starts on its own only in `prod`. Source credentials are dlt secrets, read from
the environment or `.env` (see `.env.example`).
