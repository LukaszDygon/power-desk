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

1. **dlt source:** `src/power_desk/ingest/<source>.py`.
   - Follow the contract in `ingest/common.py`: stream with a cursor, or a snapshot loaded with scd2.
   - Name raw tables uniquely across sources and yield payloads untouched.
   - Keep credentials in dlt secrets.
   - Register its `SPEC` in `ingest/pipelines.py`.
   - Check: unit tests with recorded payloads, monkeypatching `common.fetch_json` /
     `common.fetch_if_changed` (see `tests/fake_api.py`).
2. **Schedule:** add the raw tables to an `IngestJob` in `orchestration/jobs.py`, or add a new job.
   - Check: the "every raw table is scheduled" test passes.
3. **Export the schema:** run `scripts/backfill.py --pipelines <source> --skip-dbt` for a short
   range, then commit `ingest/schemas/<source>.schema.yaml`.
4. **Definitions:** `catalog/definitions/<source>.yml`.
   - Describe the source, its tables and its source-specific columns. Reuse shared column keys.
   - Cite official documentation: `refs` via a provider in `catalog/providers/`, or `links`.
   - Check: `catalog.refresh` then `catalog.generate`; generation fails on undocumented columns.
5. **Staging:** `transform/models/staging/<source>/stg_<source>__<table>.sql` plus
   `_<source>__models.yml`.
   - Type columns and convert times to UTC at the native grain, keeping `_dlt_load_id`.
   - Describe every column with `{{ doc('col_<key>') }}`.
   - Test key uniqueness, ranges and completeness.
   - Check: `dbt build --select staging.<source>`.
6. **Dimensions:** map the publisher's codes onto dimension keys in `transform/seeds/mappings/`.
   - Register the dataset in `seeds/dims/source_datasets.csv`.
   - Extend a dimension only for a genuinely new concept.
   - Check: the mapping integrity tests pass.
7. **Entity:** add a branch to the matching `ods` model, or create a new entity.
   - Conform grain, units and dimension keys, and keep `source_dataset`.
   - Decide precedence where sources overlap.
   - Check: `dbt build` and `uv run pytest`, including the column-coverage test.
8. **Verify:** run the ingest job, then confirm `dlt_meta.dlt_pending_loads` is empty and the loads
   appear in `dlt_meta.dlt_load_audit`.
