# Ingestion study: storing versioned publisher data with dlt

How to load large, revised publisher files (ENTSO-E File Library exports) with dlt so that every
version is kept, memory stays at streaming size, re-ingestion and failures stay correct, and the
pattern carries over to other destinations and to small, frequent loads.
Harness and raw results in `bench/ingestion/`: month loads (`prepare.py`, `case_body.py`,
`epoch.py cases/<epoch>.json`, `results.jsonl`), small loads (`micro_body.py`, `cases/micro.json`),
downstream marts (`downstream.py`, `downstream_results.jsonl`) and failure scenarios (`robustness.py`,
`robustness_results.json`).

## Method

- **Data:** one real month, `AggregatedGenerationPerType_16.1.B_C_r3` 2024-03: 847,671 rows, 96 MB,
  natural key `DateTime(UTC), ResolutionCode, AreaCode, AreaTypeCode, ProductionType`, unique.
- **Loads per case:** the month, the same month again (a redelivery), then a copy with 8,416 rows (1%)
  re-published with a later `UpdateTime(UTC)`. Row counts are checked against the expected versions.
- **Measured per stage** (extract, normalize, load): wall time, CPU (process + workers) and peak RSS
  (sampled every 50 ms), the files each stage writes, disk size and the cost of selecting current rows.
- **Environment:** dlt 1.30.0, DuckDB 1.5.5, PyArrow 26, PyIceberg 0.12, deltalake 1.6, Postgres 16.2
  (embedded, `pgserver`), macOS arm64. Each case runs alone in a fresh process; noise between two
  identical runs was ±0.5 s on the dict path and ±0.1 s on Arrow.

## Search space (epochs 1-6, 144 month runs)

| Dimension | Values tried |
|---|---|
| Item form | row dicts (dlt's `fetch_json`); Arrow batches; Arrow + dlt's `add_row_hash_to_table`; Arrow + `add_dlt_id` |
| Destination | DuckDB, DuckLake (SQLite catalog), Delta and Iceberg (filesystem), SQLite (sqlalchemy), Postgres |
| Disposition | append, upsert, scd2 (`merge_key` = natural key), insert-only and delete-insert on natural key + `UpdateTime` |
| Transformation | none (rename in dbt staging); rename in the DuckDB reader query; dlt naming `sql_cs_v1` |
| dlt settings | normalize workers 1-6; buffer 1k-100k; file rotation by items and bytes; extract compression; Parquet compression and version; typed columns; frozen contract; nesting; type detection; load and extract workers; staging truncation |
| Load file format | `insert_values` (DuckDB default), JSONL, Parquet, CSV (Postgres) |
| Memory | DuckDB `memory_limit` 256/512 MB; load packages of 1x/2x/4x the month; 6 loads in one process |
| Data size | 25%, 50%, 100% of the month (streaming check) |

## Results (median, full month)

| Design | 1st load | Reloads | Extract / normalize / load | Peak RSS | Disk |
|---|---|---|---|---|---|
| Arrow -> DuckLake, insert-only (version) | 1.9 s | 1.8 s | 1.1 / 0.1 / 0.7 | 719 MB | 14 MB |
| Arrow -> DuckLake, delete-insert (version) | 2.0 s | 1.9-2.3 s | 1.0 / 0.1 / 1.0 | 847 MB | 32 MB |
| Arrow + dlt row hash -> DuckLake, scd2 | 2.3 s | 2.2 s | 1.2 / 0.3 / 0.8 | 880 MB | 42 MB |
| Arrow -> Delta, insert-only (version) | 2.9 s | 2.6 s | 1.0 / 0.2 / 1.8 | 826 MB | 3 MB |
| Arrow + dlt row hash -> DuckDB, scd2 | 3.0 s | 2.3 s | 1.2 / 0.4 / 1.4 | 760 MB | 36 MB |
| Arrow -> DuckDB, insert-only (version) | 3.0 s | 1.9 s | 1.2 / 0.2 / 1.5 | 641 MB | 22 MB |
| Arrow -> DuckDB, delete-insert (version) | 3.1 s | 2.5-2.6 s | 1.1 / 0.1 / 1.9 | 761 MB | 31 MB |
| Arrow -> Iceberg, append (+ dedupe downstream) | 3.2 s | 2.5 s | 1.1 / 0.1 / 2.0 | 733 MB | 8 MB |
| Arrow + dlt row hash -> Postgres (CSV), scd2, `work_mem` 256 MB | 11.4 s | 8.9-10.8 s | 1.2 / 4.4 / 5.8 | 413 MB | 147 MB |
| Arrow -> Postgres (CSV), insert-only (version) | 15.5 s | 16.2-19.0 s | 1.8 / 6.2 / 7.5 | 498 MB | 130 MB |
| Dicts -> DuckDB, scd2, 4 normalize workers | 12.5 s | 12.0 s | 4.9 / 6.0 / 1.5 | 1,588 MB | 48 MB |
| Dicts -> DuckDB, scd2 (current repo design) | 23.5 s | 23.0 s | 5.7 / 15.7 / 2.1 | 892 MB | 48 MB |
| Dicts -> SQLite, scd2 | 35.0 s | 49.8 s | 5.6 / 16.0 / 13.4 | 712 MB | 328 MB |
| Dicts -> Postgres, scd2, `work_mem` 256 MB | 36.8 s | 33.9-34.7 s | 4.9 / 20.3 / 11.6 | 544 MB | 154 MB |

Every design produced the expected versions. scd2 on Postgres at the 4 MB `work_mem` default did not
finish a month in 20 minutes (its retire step, `NOT IN (subquery)`, can only be hashed within
`work_mem`). Delete-insert is not offered by dlt on Delta.

## Where the time goes

- **dlt's normalize of row dicts is the bottleneck: 14-21 s CPU per month.** The profile is per-row
  Python: JSON-lines round trip between extract and normalize, type coercion, flattening and
  timestamp parsing (two per row). The merge itself costs 1-2 s; the scd2 row hash about 3%.
- **Arrow skips it** (0.1-0.4 s). dlt computes no row hash for Arrow, so scd2 needs dlt's
  `add_row_hash_to_table` (pandas, per batch); `add_dlt_id` gives random ids, so every redelivered
  row becomes a new scd2 version (3x the rows). Insert-only or delete-insert on a version key need none.
- **Load file format:** DuckDB's default `insert_values` costs 44-63 s of load per month; JSONL makes
  Arrow convert to JSON in normalize (8 s); Parquet loads in 1-2 s.
- **Parallel normalize** cuts the dict path to 11-13 s but extract stays serial (~5 s), CPU rises to
  17-23 s, and each worker adds 250-300 MB.
- **Buffer 20k-100k** keeps the time and lowers dict-path peak memory by about 200 MB; Parquet row
  groups follow the buffer (dicts) or batch size (Arrow), not `row_group_size`.
- **Settings without effect** (epoch 5, within noise): extract compression (faster extract, 50x larger
  files), Parquet compression and version, file rotation, typed columns, frozen contract, nesting off,
  type detection off, load and extract workers, staging truncation, batch size beyond 50k, naming,
  renaming in the reader query.

## Memory

- **Baseline ~370 MB** (dlt, DuckDB, PyArrow imported). Extract and normalize add 70-170 MB, bounded
  by batch and buffer size, not by data size; the reader alone adds 55-110 MB per monthly file.
- **No leak:** six loads in one process plateau (Arrow ~600 MB, dicts ~970 MB, dlt row hash ~770 MB).
- **The load stage grows with the load package:** 1x/2x/4x the month in one package raised it by
  82/212/487 MB (DuckDB in-process). DuckDB `memory_limit=256MB` held 4x at 471 MB total (load 4.6 s
  instead of 2.1 s, spilling to disk). A year therefore stays at streaming size when each load package
  is bounded (a month per run) and/or DuckDB has a memory limit.

## Generalisation across destinations

| Destination | scd2 | upsert | insert-only | delete-insert | Notes |
|---|---|---|---|---|---|
| DuckDB / DuckLake | yes | yes | yes | yes | DuckLake fastest; SQLite / DuckDB catalogs load sequentially only |
| Delta (filesystem) | no | yes | yes | no | smallest on disk |
| Iceberg (filesystem) | no | crashes / hangs | crashes / hangs | not tried | PyIceberg merges build one filter from every key: >14 CPU-min for 85k rows (PyArrow 21), native crash with PyArrow 26; append works |
| SQLite (sqlalchemy) | yes | no | no | yes (dlt) | merge 13 s and growing |
| Postgres | yes, with `work_mem` | yes | yes | yes (dlt) | Arrow + CSV loads through `COPY` and skips the normalizer |

## Small, frequent loads (100 runs of 1-10 rows, one process)

| Destination | Per run (10 rows) | Load part | Upsert per run | 100 events in one run | Table files after 100 runs |
|---|---|---|---|---|---|
| SQLite | 102 ms | 24 ms | not supported | 0.18 s | - |
| Postgres | 106 ms | 25 ms | 112 ms | 0.19 s | - |
| DuckDB | 133 ms | 48 ms | 147 ms | 0.24 s | - |
| DuckLake (SQLite catalog) | 347 ms | 261 ms | 452 ms | 0.66 s | 0 (rows inlined into the catalog up to 10 per load); 100 with upsert or 100-row loads |
| Delta | 1,207 ms | 1,125 ms | 1,237 ms | 1.40 s | 101 |

- dlt itself costs about 80 ms per run (extract ~60, normalize ~20); 1 and 10 rows cost the same;
  importing dlt adds 0.25-0.8 s per new process. Item form and settings made no difference.
- Compaction: DuckLake flush + `merge_adjacent_files` 0.11-0.14 s (4 files left); Delta compact +
  vacuum 0.09 s (2 left). dlt's working folder keeps ~7 files per run (705 after 100 runs).

## Downstream: 5M-row histories at 1 to 1,000 versions per key (DuckDB)

- **Cost follows keys, not versions.** A full current-version mart took 0.4-2.9 s with one version
  per key and 5-130 ms with 100-1,000 (scd2 `_dlt_valid_to is null`, or `arg_max` on insert-only).
  `arg_max` beat `row_number` 3.7x at one version per key and tied at 100+; `distinct on` was slowest.
- **Incremental updates by `_dlt_load_id`** took 6-84 ms in every profile. Validity windows derived
  from insert-only rows (`lead`) took 0.6-0.8 s, scaling with rows.
- **Uneven profiles** (90/10, 99/1, Zipf with one key at 438,596 versions) cost nothing measurable.
- **Raw storage** was 108-160 MB per 5M rows in both layouts. A 5,000-row dlt load on top of the
  history took 0.52 s for scd2 against 0.14 s for insert-only with 5M open versions; within 0.04 s
  with 50,000 keys or fewer.

## Re-ingestion and failures (`robustness.py`)

| Strategy (key) | Same export again | Older version after a newer one | Process killed mid-load, resumed |
|---|---|---|---|
| append | duplicated | older becomes current | duplicates |
| upsert (natural key) | no change | older overwrites newer | duplicates |
| scd2 (`merge_key` = natural key) | no change | older re-inserted as current | keys with two open versions |
| insert-only (key + `UpdateTime`) | no change | kept as history, newest current | duplicates |
| delete-insert (key + `UpdateTime`) | no change | kept as history, newest current | none |

- **A kill mid-load can load a file twice:** dlt records a job's outcome after the destination
  commits it (`resume_started_jobs`), so a kill in between re-runs the job. Duplicates appeared in
  most kills for every strategy except delete-insert, which deduplicates its staged rows.
- **Mid-run failures otherwise recover:** an extract failure keeps nothing; a crash after normalize
  leaves a pending package that the next `run()` loads before (and instead of) new data; a locked
  destination leaves the package pending and `load()` completes it. Since dlt 1.30
  `drop_pending_packages()` is an alias of `abort_packages()`, which discards and rewinds.
- **State:** a lost working folder is restored from `_dlt_pipeline_state`; a lost destination dataset
  makes dlt wipe the whole working folder, including completed packages, and start over.
- **Recovery:** a plain rerun reloads only what the source offers now (ENTSO-E: latest exports).
  Copying the completed packages' Parquet files out of the working folder first, then replaying them
  oldest first, restored scd2 and insert-only exactly; rows keep their old `_dlt_load_id` and scd2
  validity starts at the replay. dlt has no replay command; filesystem staging for warehouses keeps
  files only with `truncate_tables_on_staging_destination_before_load = false`.

## Findings that affect the code

- dlt's `fetch_json` calls `DuckDBPyRelation.fetchmany`, removed in DuckDB 2.0; pin or replace it.
- Arrow tables get `_dlt_load_id` only with `normalize.parquet_normalizer.add_dlt_load_id=true`.
- Parallel normalize spawns processes that import `__main__`: entry points must be import-safe.
- DuckDB's `fetch_arrow_reader` is deprecated in favour of `to_arrow_reader`.
- `ingest/pipeline.py` retries lock errors with `drop_pending_packages()`, which now aborts the
  package; dlt recommends retrying `load()`.
- ENTSO-E's scd2 resources set `primary_key`, which dlt's scd2 merge does not use.

## Recommendation

Decision for now: keep dlt's defaults for maintainability and portability
([ADR 0001](adr/0001-keep-dlt-defaults-for-ingestion.md)). The fastest and most robust designs measured:

1. **ENTSO-E: Arrow batches + delete-insert on natural key + `UpdateTime`** into DuckDB (or
   DuckLake): 2-3 s per month, streaming memory, idempotent, independent of arrival order, and the
   only strategy without duplicates after a mid-load kill. Validity windows are derived downstream;
   a revision that does not change `UpdateTime` is missed.
2. **Arrow + dlt's `add_row_hash_to_table` + scd2** gives validity windows in the table at the same
   speed, but its current version follows arrival order and it duplicates after a mid-load kill.
3. **Row dicts with dlt's default hashing** (current repo design): simplest code, 8-10x slower.

In every case: Parquet load files, one monthly file per load package, DuckDB `memory_limit` for
backfills, renaming in dbt staging, marts built incrementally by `_dlt_load_id`, and a copy of
loaded files kept outside dlt's working folder. Small, frequent sources: batch before dlt and land in
a row store, or DuckLake with inlining and scheduled compaction.

## Open avenues (not ruled out)

- DuckLake with a Postgres catalog (parallel loads); Delta merge at year scale; Iceberg through a REST
  catalog or a newer PyIceberg; Arrow row hash without pandas once dlt adds it (TODO in dlt's Arrow
  normalizer); a year of data to confirm per-package memory bounds end to end; whether
  `load.workers=1` removes the kill-time duplicates; Snowflake staging and Time Travel in practice.
