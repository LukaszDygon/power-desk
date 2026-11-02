# Kind: snapshot (a whole reference file, re-read each time)

**Model:** `ingest/sources/entsoe_eic.py`: one `Snapshot` per file (URL, parser, natural key), and
`changed_rows` skips a file whose ETag or content hash is unchanged.

- **Change detection:** `http.fetch_if_changed(url, etag)`. Validators are kept in resource state
  (`source_file`), so an unchanged file costs one request and loads nothing.
- **Disposition:** `merge` + `scd2`, no `merge_key`: the full extract closes every key missing from it,
  so withdrawn codes keep their history (`_dlt_valid_from`, `_dlt_valid_to`). `primary_key` = natural
  key, which documents it and drives the uniqueness guard.
- **Parsing:** use the standard library (`csv`, `html.parser`) or DuckDB `read_csv`. Rows go out as
  published.
- **Schedule:** daily or slower (`refresh_reference`), as the publisher regenerates the file.
- **Seed:** the recorded file in `elt/seed/<source>/`, served by `SeedPublishers.fetch_if_changed`.
- **Pitfall:** never use it for partial files. A `scd2` load without `merge_key` closes everything that
  isn't in the load.
