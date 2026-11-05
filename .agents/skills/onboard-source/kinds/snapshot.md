# Kind: snapshot (a whole reference file, re-read each time)

**Model:** `ingest/sources/entsoe_eic.py`: one `Snapshot` per file (URL, parser, natural key), and
`changed_rows` skips a file whose ETag or content hash is unchanged. A file published at a new address
per release takes a lookup of the current one as its URL (`desnz_repd.py`: `current_extract_url`).

- **Change detection:** `http.fetch_if_changed(url, etag)`. Validators are kept in resource state
  (`source_file`), so an unchanged file costs one request and loads nothing.
- **Disposition:** `merge` + `scd2`, no `merge_key`: the full extract closes every key missing from it,
  so withdrawn codes keep their history (`_dlt_valid_from`, `_dlt_valid_to`). `primary_key` = natural
  key, which documents it and drives the uniqueness guard.
- **Parsing:** structured files (CSV, JSON) are read as published (`csv`, `json`, DuckDB `read_csv`):
  no renames, drops, cleaning or derived values. Unstructured ones (an HTML table) are parsed by a pydantic
  data class owning its parser (`entsoe_eic.IssuingOffice.parse`, over the generic `HtmlTable`), which
  keys cells by the header text as published and keeps their text, link address or icon names; staging
  derives the rest (e.g. booleans from icons).
- **Schedule:** daily or slower (`refresh_reference`), as the publisher regenerates the file.
- **Seed:** the recorded file in `elt/seed/<source>/`, served by `SeedPublishers.fetch_if_changed`.
- **Pitfall:** never use it for partial files. A `scd2` load without `merge_key` closes everything that
  isn't in the load.
