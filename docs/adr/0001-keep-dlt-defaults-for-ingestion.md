# ADR 0001: Keep dlt's default row handling for ingestion

- **Status:** accepted, 2026-10-28; amended 2026-10-28 (streams: `upsert` -> `delete-insert`)
- **Evidence:** [ingestion study](../ingestion-study.md); harness and raw results in `bench/ingestion/`

## Context

Sources yield row dicts; dlt types, names and hashes them, then loads Parquet files into DuckDB.
ENTSO-E monthly exports (about 100 MB, re-published when revised) load with `scd2` on the natural
key, Elexon and PVLive with `delete-insert` on the natural key, EIC snapshots with `scd2`
([write dispositions](../architecture.md#write-dispositions)).

We measured the alternatives: 144 runs on one real ENTSO-E month (item forms, six destinations, five
merge strategies, about twenty dlt settings), 39 small-load cases (1-10 rows per run), mart builds on
5M-row histories at 1-1,000 versions per key, and failure, replay and recovery scenarios.

## Decision

Keep dlt's default behaviour: yield row dicts and let dlt infer types, normalize names and compute
row ids; keep the current merge strategies. The only non-default setting stays Parquet load files.

**Why:** maintainability and portability. Every resource is written the same way whatever the source
or destination, with no Arrow plumbing, no own hashing or version columns, and dlt owning typing,
naming and row identity. Moving to another dlt source or destination changes configuration, not
resource code.

## Consequences

- **Cost:** about 21-23 s per ENTSO-E month, mostly dlt's per-row normalize (14-21 s CPU); a year is
  about 12 runs. Memory stays at streaming size (peak under 900 MB per month).
- **Known risks**, measured, to keep in mind:

| Risk | What happens | Mitigation without changing the design |
|---|---|---|
| Older data arrives after newer | `scd2` and `delete-insert` make the older version current | Unlikely today: the File Library only offers each file's latest export. Do not replay older copies; marts that pick the newest `UpdateTime` stay correct |
| Process killed mid-load | dlt records a job's outcome after the destination commits it, so a resumed load can repeat a file: duplicates, or keys with two open `scd2` versions | Add dbt tests (one open version per key; one row per key and version) and reload the affected month when they fail |
| Destination dataset lost | dlt wipes its working folder, including the loaded files, and reloads only what the source offers now (ENTSO-E: latest exports, no history) | Back up the warehouse file; copy loaded files out of the pipeline folder before any rerun |
| Warehouse locked during a load | `ingest/pipeline.py` retries with `drop_pending_packages()`, which since dlt 1.30 aborts the package and rewinds state; the next run re-extracts | Acceptable; retrying `pipeline.load()` instead would avoid the re-extract |
| Postgres as destination | `scd2`'s `NOT IN` check does not finish on a month at the 4 MB `work_mem` default | Raise `work_mem` (256 MB: 9-37 s per month) |

ENTSO-E's `scd2` resources also set `primary_key`, which dlt's `scd2` merge does not use; it only
documents the key in the dlt schema.

## Most efficient avenues, if we revisit

1. **Arrow batches instead of row dicts** (DuckDB `to_arrow_reader`): 2-3 s instead of 21-23 s per
   month. dlt adds no row hash to Arrow, so it needs a version key (below) or `add_row_hash_to_table`
   (pandas) for `scd2`.
2. **`delete-insert` on natural key + `UpdateTime`:** idempotent, independent of arrival order, and
   the only strategy without duplicates after a mid-load kill (0 of 13 kills); 0.2-0.5 s per month
   more than `insert-only`. Validity windows move to dbt. Not offered by dlt on Delta.
3. **Four normalize workers** (with `file_max_items`): keeps row dicts, about 12 s per month, at
   250-300 MB more memory per worker.
4. **`buffer_max_items` 20k-100k:** same speed, about 200 MB less peak memory on the dict path.
5. **DuckLake** instead of one DuckDB file: the fastest destination tested (1.6-2.3 s per month with
   Arrow); keeps Parquet files plus a catalog, and inlines loads of up to 10 rows.
6. **Small, frequent sources:** batch before dlt (100 events in one run: 0.2-1.4 s; as 100 runs:
   10-120 s) and land them in a row store or DuckLake.
7. **Recovery:** keep a copy of loaded files outside dlt's working folder, e.g. a second pipeline
   appending the same rows to object storage; dlt has no replay command.

Settings that made no difference are listed in the study, so they need not be tried again.

**Amendment (2026-10-28):** a full reload from 2024-01-01 found Elexon NDF records the API returns two
or three times verbatim within a day (1,259 keys); `upsert` keeps every copy of a key within one load,
failing the raw uniqueness test. Streams now use dlt's `delete-insert` on the same primary key, which
keeps one row per key within a load and replaces it on republication. Still a dlt default strategy;
`_dlt_id` is a row id rather than a hash of the primary key.

## Revisit when

- Ingestion time starts to matter: multi-year backfills or many more data items.
- The destination moves to Delta or Iceberg (no `scd2` in dlt) or Postgres (`work_mem`).
- Duplicates or out-of-order replays show up in practice (the dbt tests above).
- dlt computes a row hash for Arrow tables (a TODO in its Arrow normalizer), removing the main cost of avenue 1.
