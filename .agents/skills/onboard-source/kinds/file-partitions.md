# Kind: file partitions (periodic files the publisher re-exports when revised)

**Model:** `ingest/sources/entsoe.py`: a table of `DataItem`s (folder, natural key), `plan_files`
picks the files new or changed since the last load (`lastUpdated` in resource state), within
`max_days` of periods per run.

- **Reading:** stream each file to disk and read it with DuckDB (`read_csv`), then yield batches with
  dlt's `fetch_json(relation, BATCH_ROWS)`. Memory stays at batch size, and DuckDB infers the types.
- **Disposition:** `merge` + `scd2`, `merge_key` = `primary_key` = natural key. A revision closes the
  row's previous version, a row missing from a re-export stays current, and the same row may arrive in
  several files. If an export lists several documents per key, the document id joins `primary_key` only.
- **Cursor:** the latest publication time in the files (`UpdateTime`), since a re-export is new data.
- **Seed:** recorded files, gzipped, in `elt/seed/<source>/` (a month, cut to the seed week if large),
  served by `SeedPublishers` (`list_folder`, `download`).
- **Staging:** `incremental`, `delete+insert` on the natural key, `meta={'dlt_tracked': true}`, reading
  `where _dlt_valid_to is null and {{ dlt_incremental_filter('_dlt_load_id') }}`.
