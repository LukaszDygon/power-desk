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
| `raw` | dlt tables, one per resource | As published, merged on the natural key (snapshots: scd2). Never edited. |
| `staging/<source>` | views, one per raw table | Types, UTC time, source-specific dedup, shared column vocabulary. |
| `ods` | views, one per entity | Union of every source providing the entity, conformed to one grain and to dimension keys. |
| `dims` | tables + seeds | Conformed dimensions, hierarchy bridges, and mappings from publisher codes. |
| `marts` | incremental tables | Built on `ods` + `dims`; rebuild only grains touched by pending loads. |
| `dlt_meta` | views + audit table | Which dlt load each mart processed, in which dbt / Dagster run. |

`staging`, `ods`, `dims` and `marts` may be revised as new data arrives; `raw` stays true to
the source.

## Dimensions

**Goal:** a query needs only values, a datetime, and the natural keys of a small set of shared
dimensions; the dimension tables explain what each key means and how keys relate.

- **Mart rows** are `timestamp_utc` (+ interval), dimension keys, measures, and provenance
  (`source_dataset`, `_last_dlt_load_id`).
- **Conformed dimensions:** area, border, technology, resource, party, source dataset. Each is keyed
  by a natural key (EIC code or canonical code) and versioned where its publisher revises it.
- **Bridges** relate keys across granularities (unit → plant, zone → member state, technology →
  group). Rolling a row up to any level is one join. They are graphs, not trees.
- **Mappings** (`seeds/mappings`) translate each publisher's codes into dimension keys, at the most
  specific level the publisher supports. Incompatible schemes meet on the same concepts.
- **Traceability:** an ODS row keeps its `source_dataset`, source code and `_dlt_load_id`, which
  lead back to the raw row and the dlt load that delivered it.

## Ingestion

- **Contract:** each source module follows `ingest/common.py` and registers a `SourceSpec` in
  `ingest/pipelines.py`. Raw payloads are yielded untouched.
- **Streams** have one cursor per resource and fetch at most `max_days_per_run` new days from it.
  Bounded backfills leave the cursor untouched. Fetch errors fail the run, so no gap is skipped.
- **Snapshots** (reference files) re-read the whole file, skip it while unchanged (ETag / hash), and
  load with scd2, so changes and withdrawals keep their history.
- **dlt schemas** are exported to `ingest/schemas/` and define the dbt sources.

## Orchestration

- **`orchestration/jobs.py`** groups raw tables by publication cadence. Each entry yields a job, a
  schedule, cursor-lag checks and a catch-up branch.
- **Every ingest job builds all dbt models.** Models over a never-loaded raw table are skipped.
- **The catch-up sensor** re-runs a job while its last run was capped.
- **Nightly** runs every test unscoped and refreshes dbt docs.
- **One run at a time:** DuckDB allows a single writer.

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
| Natural-key / row-version uniqueness | raw | blocks |
| Key uniqueness, ranges, completeness | staging | blocks; completeness warns in scheduled runs, errors nightly |
| Entity-key uniqueness, dimension keys resolve | ods | blocks; unmapped codes warn |
| Mapping keys exist in their dimension | dims | blocks |
| Grain uniqueness, fan-out, business rules | marts | blocks; business rules may warn |

Failing rows are stored in `test_failures.<test>`.

## Catalogue

- **Definitions:** `catalog/definitions/*.yml` define each table and column concept once. They cite
  official sources as provider references (`provider:kind/id`, fetched into `catalog/snapshots/`) or
  as document links.
- **Generation:** `catalog.generate` writes one dbt doc block per definition, plus the dbt sources.
  Models reference the blocks with `{{ doc() }}`.
- **Coverage:** generation fails on undocumented raw columns, and tests fail on undocumented
  warehouse columns.

## Environments

`POWER_DESK_ENV` (`dev`, `prod`) selects the warehouse file, dbt target, dlt state and Dagster
instance. Automation starts on its own only in `prod`.
