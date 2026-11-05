---
name: onboard-source
description: >-
  Onboards a publisher (a new dlt source) or a new dataset of an existing source into the
  warehouse, stage by stage: ingestion, seed, catalogue and freshness, schedule, staging,
  dimensions, entity, marts, contracts and an acceptance run. Use when adding a source or a raw
  table, or when combining a new feed with existing entities; phase 4 of onboard-dataset.
---

# Onboard a Source or Dataset

Rules: `docs/architecture.md`. Ingestion design: [ADR 0001](../../../docs/adr/0001-keep-dlt-defaults-for-ingestion.md)
(keep dlt's defaults); onboarding defaults: [ADR 0003](../../../docs/adr/0003-onboarding-defaults.md). Go stage by
stage; each check must pass before the next. For a new dataset of an existing source, extend that source's
table of datasets and skip what already exists. The design comes from the agreed `scope.md`
(`onboard-dataset`); a change to it is a deviation to report. **No agreed `scope.md` in your own worktree?**
Then run `onboard-dataset` from phase 0 (worktree, profile, scope stop) before stage 0 here.

## 0. Decide before coding

- **Kind** (`docs/architecture.md`, Ingestion), which fixes the state, disposition and key. Read the kind's
  reference before coding; every kind loads with `scd2` (time travel) unless the user confirmed otherwise:

| Kind | Reference | Model source | Progress kept in | Keys |
|---|---|---|---|---|
| Stream (API by publication or update time) | [kinds/stream.md](kinds/stream.md) | `neso.py` | `dlt.sources.incremental` + `incremental_window` | `merge_key` = natural key |
| Snapshot (whole reference file) | [kinds/snapshot.md](kinds/snapshot.md) | `entsoe_eic.py` | ETag / hash in resource state | `primary_key` = natural key, no `merge_key` |
| File partitions (re-exported periodic files) | [kinds/file-partitions.md](kinds/file-partitions.md) | `entsoe.py` | files + `lastUpdated` in resource state | `merge_key` = `primary_key` = natural key |
| Gridded forecast runs (GRIB fields, values at points) | [kinds/gridded.md](kinds/gridded.md) | `ecmwf.py` | run date (incremental) | `merge_key` = natural key incl. the run |

  Nested payloads, whatever the kind: [kinds/nested.md](kinds/nested.md). Existing Elexon and PVLive streams
  load with `delete-insert` (ADR 0001); a new stream does so only as a confirmed exception.

- **Natural key and definitions** come from the publisher's documentation, never invented; cite it.
- **Entity:** which `ods_<entity>` the data feeds, or whether it is a new one.

## 1. Ingest

`elt/src/power_desk_elt/ingest/sources/<source>.py`, shaped like the existing sources: a table of datasets, fetch
functions, a `@dlt.source(window: RunWindow)` and a `SPEC`.
- Name raw tables `<source>__<dataset>`. Yield rows (dicts) as published, in pages (e.g. 50,000 rows), never
  one row per `yield`: no renames, no added columns, no ingestion timestamps (dlt's `_dlt_load_id` is the
  only one). dlt infers types and computes row ids.
- Set the disposition and keys for the kind, and `file_format="parquet"` (DuckDB's default is 30-50x slower).
- Fetch through `ingest/http.py` or the publisher's client; stream large files to disk and read them in
  batches (DuckDB `read_csv` + dlt's `fetch_json`, as `entsoe.py` does), so memory stays at batch size.
- Credentials are dlt secrets (`.env`, listed in `.env.example`), resolved at run time.
- Register the `SPEC` in `ingest/registry.py`, with `max_days_per_run` (and `window_padding_days` if the
  publisher's local dates cross UTC days).
- Check: unit tests for parsing and planning in `elt/tests/unit/`; `make check-elt`.

## 2. Seed

Serve the publisher offline from `ingest/seed/replay.py` (`SeedPublishers`): recorded files in
`elt/seed/<source>/` for exports and reference files, synthetic records in `ingest/seed/synthetic.py` for
API streams.
- The replay stands in for the fetch function, so it can't show how the real client answers "not published
  yet" or an error (dlt's client raises on 404). Unit-test those against the real client.
- Check: `elt/tests/integration/test_ingest.py` loads every published row (add a case for the new table);
  `uv run power-desk-load-seed` builds the dev warehouse.

## 3. Export the dlt schema

One month of `backfill_<source>` on the real publisher writes `ingest/schemas/<source>.schema.yaml` (dlt's
names: `DateTime(UTC)` becomes `date_time_utcx`): launch it in the Dagster UI, or in a scratch script,
`defs.resolve_job_def("backfill_<source>").execute_in_process(partition_key="<yyyy-mm-01>")` with `defs` from
`power_desk_elt.orchestration.definitions`.
Commit it; it defines the dbt source. This puts real rows into the dev warehouse, and contracts take their
types from it, so rebuild it from the seed afterwards: `uv run power-desk-load-seed --fresh`. Trial loads go
into a scratch warehouse file (`make_pipeline(name, path)` keeps dlt state per file).

## 4. Catalogue and freshness

`elt/src/power_desk_elt/catalog/definitions/<source>.yml`: `sources`, `tables` (title, description, `url`,
`freshness`) and source-specific `columns`; reuse shared column keys.
- Cite official documentation with `refs` (a provider in `catalog/providers/`) or `links` (with
  `section` / `page`); descriptions hold the definition only.
- `freshness` names a preset in `platform.yml` (`actuals`, `forecasts`, `daily_exports`, ...; add one for
  a new cadence). It drives dbt source freshness and the Dagster `recently_fetched` / `recent_data` checks.
- Check: `uv run python -m power_desk_elt.catalog.refresh --provider <yours>` (network; without
  `--provider` it rewrites every provider's retrieval dates, which conflicts with parallel sessions), then
  `... catalog.generate` and `uv run dbt parse --project-dir elt/dbt --profiles-dir elt/dbt` (Dagster reads
  the manifest); generation fails on undocumented raw columns.

## 5. Schedule

Add each raw table to exactly one `IngestJob` in `orchestration/jobs.py`, by publication cadence, or add a
job (schedule and catch-up come with it).
- Check: `elt/tests/integration/test_orchestration.py`; loading the definitions fails while a raw table is
  unscheduled.

## 6. Staging

`elt/dbt/models/staging/<source>/stg_<source>__<table>.sql` plus `_<source>__models.yml`.
- Read with `{{ dlt_source('<source>', '<table>') }}`; type columns, convert times to UTC at the native
  grain, rename dlt's names, keep `_dlt_load_id`.
- File partitions: `incremental`, `delete+insert` on the natural key, `meta={'dlt_tracked': true}`, reading
  `where _dlt_valid_to is null and {{ dlt_incremental_filter('_dlt_load_id') }}`. Snapshots keep validity
  with `{{ scd2_validity() }}`. Streams: plain views.
- An incremental model's `unique_key` is raw's row-level natural key, never a coarser one (a run, a day):
  `delete+insert` on a coarse key rewrote whole runs (383 s against 0.9 s keyed by row), and a key that
  misses a column of raw's left stale rows behind.
- Describe every column with `{{ doc('col_<key>') }}`; test key uniqueness, ranges and completeness.
- Check: `uv run dbt build --project-dir elt/dbt --profiles-dir elt/dbt --select staging.<source>`.

## 7. Dimensions

Map the publisher's codes onto dimension keys in `elt/dbt/seeds/mappings/`, register the dataset in
`seeds/dims/source_datasets.csv`, and extend a dimension only for a genuinely new concept (with an
authoritative definition).
- Check: the mapping integrity tests pass.

## 8. Entity

Add a branch to the matching `ods_<entity>`, or create a new entity (`ods.yml`, plus its hourly mart in
`marts/combined/` built with `hourly_series`).
- Conform units and dimension keys (horizons from `dim_time_horizon`); keep the published interval,
  `publish_time_utc`, `source_dataset`, the source code and `_dlt_load_id`, in the column order of
  `docs/architecture.md` (Naming). Keep every resolution published: the hourly mart resolves overlaps
  (most recently published wins) and records `coverage`.
- Name each measure in `seeds/dims/metrics.csv` with its hourly aggregation (`mean` for MW, prices and
  capacities; `sum` for volumes), and pass it to `hourly_series` the same way.
- Read each staging model through `pending_partitions(ref(...), [area key])`, so an incremental build
  transforms only the (area, hour) partitions pending loads touch.
- Check: `dbt build` and `make check-elt`, including the warehouse column-coverage test.

## 9. Marts and dashboard

- Business marts (`mart_<scope>_<subject>`) are incremental on pending loads (Load-id contract); add or
  extend one only when the data answers a new question, with grain and business-rule tests.
- Cards: the `create-widget` skill.

## 10. Data contracts

The changed entities and marts get their contracts from their dbt tests and `meta`
([data contracts](../../../docs/data-contracts.md)).
- Give every new dimension key a `relationships` test, and every new rule for querying the data (a new
  area level, an overlapping source, a horizon to pick) a `context` constraint: the `verify-contract` skill.
- Check: on the seed week (`uv run power-desk-load-seed --fresh`), `uv run python -m power_desk_elt.catalog.contracts`;
  review `git diff elt/contracts`.

## 11. Verify end to end

`uv run power-desk-accept <source> --start-date <d> --end-date <d> --resources <new tables>` on the real
publisher (`--resources` limits it to the datasets being onboarded, so an existing source's other datasets
are neither fetched nor judged): a fresh warehouse (EIC seed for the dimensions plus the source), then loading,
structure, idempotency (the last day loaded again), time travel, `dlt.load` events, dbt tests, `dim_source_dataset`, an hourly mart, the schedule budget
and query time, with a profile and CSV samples of every relation holding the source's rows
(`data/onboarding/<source>/acceptance/`). Every criterion passes or is a confirmed exception, and `make check`
is green.

## Pitfalls (measured, see `docs/adr/evidence/0001-ingestion-study.md`)

- A `scd2` resource without `merge_key` closes every key missing from a load: right for full snapshots,
  wrong for partial files.
- The cursor of revised data is its publication time (`UpdateTime`), not the value's date.
- Never edit or backfill `raw` by hand; replaying older data makes it current under `scd2` and `delete-insert`.
- Arrow tables get no row hash from dlt, so `scd2` cannot run on them (ADR 0001 lists when to revisit).
