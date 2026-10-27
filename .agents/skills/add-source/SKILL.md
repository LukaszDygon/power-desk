---
name: add-source
description: >-
  Adds a data source (publisher) end to end: dlt source, schedule, catalogue definitions, dbt
  staging, dimension mappings and entity integration. Use when onboarding a publisher or
  combining a new feed with existing entities.
---

# Add a Data Source

The rules are in `docs/architecture.md`. Follow the steps in order; each step's check must pass
before the next.

1. **dlt source:** `src/power_desk/ingest/sources/<source>.py`, shaped like the existing ones: a table
   of datasets, fetch functions, a `@dlt.source(initial_date, end_date, max_days_per_run)` and a `SPEC`.
   - Pick the ingestion kind in `docs/architecture.md`: stream (`ingest/windows.py`), snapshot (scd2)
     or file partitions (`merge_key` per file). Fetch through `ingest/http.py`.
   - Name raw tables `<source>__<dataset>` and yield payloads untouched.
   - Keep credentials in dlt secrets (`.env`, listed in `.env.example`), resolved at run time.
   - Register the `SPEC` in `ingest/registry.py`.
2. **Seed:** record a small extract of the publisher's payloads for the seed week in `data/seed/<source>/`
   and serve it from `ingest/seed/replay.py`.
   - Check: `tests/integration/test_ingest.py` loads every published row; add unit tests for parsing.
3. **Schedule:** add the raw tables to an `IngestJob` in `orchestration/jobs.py`, or add a new job;
   importing the orchestration fails while a raw table is unscheduled.
4. **Export the schema:** run `power-desk-backfill --sources <source> --skip-dbt` for a short
   range, then commit `ingest/schemas/<source>.schema.yaml`.
5. **Definitions:** `catalog/definitions/<source>.yml`.
   - Describe the source, its tables and its source-specific columns. Reuse shared column keys.
   - Cite official documentation with `refs` (a provider in `catalog/providers/`) or `links` (with
     `section` / `page`). Citations become `meta.references`; descriptions hold the definition only.
   - Check: `catalog.refresh` then `catalog.generate`; generation fails on undocumented columns.
6. **Staging:** `transform/models/staging/<source>/stg_<source>__<table>.sql` plus
   `_<source>__models.yml`.
   - Read raw tables with `{{ dlt_source() }}`; type columns and convert times to UTC at the native
     grain, keeping `_dlt_load_id`.
   - Describe every column with `{{ doc('col_<key>') }}`.
   - Test key uniqueness, ranges and completeness.
   - Check: `dbt build --select staging.<source>`.
7. **Dimensions:** map the publisher's codes onto dimension keys in `transform/seeds/mappings/`.
   - Register the dataset in `seeds/dims/source_datasets.csv`.
   - Extend a dimension only for a genuinely new concept.
   - Check: the mapping integrity tests pass.
8. **Entity:** add a branch to the matching `ods` model, or create a new entity.
   - Conform grain, units and dimension keys, and keep `source_dataset`.
   - Decide precedence where sources overlap.
   - A new entity also gets a view in `marts/combined/`.
   - Check: `dbt build` and `uv run pytest`, including the column-coverage test.
9. **Verify:** run the ingest job, then confirm `dlt_meta.dlt_pending_loads` is empty and the loads
   appear in `dlt_meta.dlt_load_audit`.
