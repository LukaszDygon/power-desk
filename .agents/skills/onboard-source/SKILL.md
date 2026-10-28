---
name: onboard-source
description: >-
  Onboards a publisher (a new dlt source) or a new dataset of an existing source into the
  warehouse, stage by stage: ingestion, seed, catalogue and freshness, schedule, staging,
  dimensions, entity, marts and dashboard. Use when adding a source or a raw table, or when
  combining a new feed with existing entities.
---

# Onboard a Source or Dataset

Rules: `docs/architecture.md`. Ingestion design: [ADR 0001](../../../docs/adr/0001-keep-dlt-defaults-for-ingestion.md)
(keep dlt's defaults). Go stage by stage; each check must pass before the next. For a new dataset of an
existing source, extend that source's table of datasets and skip what already exists.

## 0. Decide before coding

- **Kind** (`docs/architecture.md`, Ingestion), which fixes the state, disposition and key:

| Kind | Example | Progress kept in | Disposition | Keys |
|---|---|---|---|---|
| Stream (API by publish time) | Elexon, PVLive | `dlt.sources.incremental` + `incremental_window` | `merge` + `delete-insert` | `primary_key` = natural key |
| Snapshot (whole reference file) | EIC | ETag / hash in resource state | `merge` + `scd2`, no `merge_key` | `primary_key` = natural key (documents it) |
| File partitions (re-exported periodic files) | ENTSO-E | files + `lastUpdated` in resource state; cursor = latest publication time | `merge` + `scd2` | `merge_key` = `primary_key` = natural key (a document id joins `primary_key` where an export repeats keys) |

- **Natural key and definitions** come from the publisher's documentation, never invented; cite it.
- **Entity:** which `ods_<entity>` the data feeds, or whether it is a new one.

## 1. Ingest

`src/power_desk/ingest/sources/<source>.py`, shaped like the existing sources: a table of datasets, fetch
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
- Check: unit tests for parsing and planning in `tests/unit/`; `uv run pyright`.

## 2. Seed

Serve the publisher offline from `ingest/seed/replay.py` (`SeedPublishers`): recorded files in
`data/seed/<source>/` for exports and reference files, synthetic records in `ingest/seed/synthetic.py` for
API streams.
- Check: `tests/integration/test_ingest.py` loads every published row (add a case for the new table);
  `uv run power-desk-load-seed` builds the dev warehouse.

## 3. Export the dlt schema

`uv run power-desk-backfill --sources <source> --start-date <d> --end-date <d> --skip-dbt` for a short range
writes `ingest/schemas/<source>.schema.yaml` (dlt's names: `DateTime(UTC)` becomes `date_time_utcx`).
Commit it; it defines the dbt source.

## 4. Catalogue and freshness

`src/power_desk/catalog/definitions/<source>.yml`: `sources`, `tables` (title, description, `url`,
`freshness`) and source-specific `columns`; reuse shared column keys.
- Cite official documentation with `refs` (a provider in `catalog/providers/`) or `links` (with
  `section` / `page`); descriptions hold the definition only.
- `freshness` names a preset in `platform.yml` (`actuals`, `forecasts`, `daily_exports`, ...; add one for
  a new cadence). It drives dbt source freshness and the Dagster `recently_fetched` / `recent_data` checks.
- Check: `uv run python -m power_desk.catalog.refresh` (network), then `... catalog.generate`; generation
  fails on undocumented raw columns.

## 5. Schedule

Add each raw table to exactly one `IngestJob` in `orchestration/jobs.py`, by publication cadence, or add a
job (schedule and catch-up come with it).
- Check: `tests/integration/test_orchestration.py`; loading the definitions fails while a raw table is
  unscheduled.

## 6. Staging

`transform/models/staging/<source>/stg_<source>__<table>.sql` plus `_<source>__models.yml`.
- Read with `{{ dlt_source('<source>', '<table>') }}`; type columns, convert times to UTC at the native
  grain, rename dlt's names, keep `_dlt_load_id`.
- File partitions: `incremental`, `delete+insert` on the natural key, `meta={'dlt_tracked': true}`, reading
  `where _dlt_valid_to is null and {{ dlt_incremental_filter('_dlt_load_id') }}`. Snapshots keep validity
  with `{{ scd2_validity() }}`. Streams: plain views.
- Describe every column with `{{ doc('col_<key>') }}`; test key uniqueness, ranges and completeness.
- Check: `uv run dbt build --project-dir transform --profiles-dir transform --select staging.<source>`.

## 7. Dimensions

Map the publisher's codes onto dimension keys in `transform/seeds/mappings/`, register the dataset in
`seeds/dims/source_datasets.csv`, and extend a dimension only for a genuinely new concept (with an
authoritative definition).
- Check: the mapping integrity tests pass.

## 8. Entity

Add a branch to the matching `ods_<entity>`, or create a new entity (`ods.yml`, plus a view in
`marts/combined/`).
- Conform grain, units and dimension keys; keep `source_dataset`, the source code and `_dlt_load_id`, in
  the column order of `docs/architecture.md` (Naming).
- Decide precedence where sources overlap; keep the finest resolution with `keep_finest_resolution`.
- Check: `dbt build` and `uv run pytest`, including the warehouse column-coverage test.

## 9. Marts and dashboard

- Business marts (`mart_<scope>_<subject>`) are incremental on pending loads (Load-id contract); add or
  extend one only when the data answers a new question, with grain and business-rule tests.
- Cards: the `create-widget` skill.

## 10. Verify end to end

Run the ingest job (Dagster, or `power-desk-backfill --sources <source>`), then confirm:
`dlt_meta.dlt_pending_loads` is empty, the loads appear in `dlt_meta.dlt_load_audit`, the freshness checks
pass, and `uv run pytest` and `uv run pyright` are green.

## Pitfalls (measured, see `docs/ingestion-study.md`)

- A `scd2` resource without `merge_key` closes every key missing from a load: right for full snapshots,
  wrong for partial files.
- The cursor of revised data is its publication time (`UpdateTime`), not the value's date.
- Never edit or backfill `raw` by hand; replaying older data makes it current under `scd2` and `delete-insert`.
- Arrow tables get no row hash from dlt, so `scd2` cannot run on them (ADR 0001 lists when to revisit).
