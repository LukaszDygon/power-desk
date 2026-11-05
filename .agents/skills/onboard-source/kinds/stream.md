# Kind: stream (an API read by publication or update time)

**Model:** `ingest/sources/neso.py`: a table of datasets, one resource per dataset, an upload-time
cursor and pages.

- **Cursor:** the publication or update time (`dlt.sources.incremental` on it), never the value's time.
  A revision is then new data. `incremental_window(cursor, window.max_days)` plans the days, and
  `.chunks(DAYS_PER_REQUEST)` sizes each request to the publisher's limit.
- **Disposition:** `merge` + `scd2`, `merge_key` = natural key, so a revision closes the previous
  version and keys missing from a load stay current. If the publisher may append a resubmission as a
  separate row rather than replace it, the publication time joins `primary_key` (not `merge_key`), and
  staging keeps the latest.
- **Event messages** (immutable messages, a revision being a new message, e.g. Elexon REMIT): key on the
  publisher's message id (`merge_key` = `primary_key`), flag the latest revision in staging, and rebuild
  whole events downstream (`delete_touched` pre-hook, append): a revision can drop hours, which
  `delete+insert` and `hourly_series` would keep. Model: `bmrs.py` (`remit`), ADR 0004.
- **Rows as published:** yield the API's records unchanged, its own columns included (NESO's datastore
  `_id`, `_full_text`), with only the column names it lists (PVLive's `meta`), never invented ones.
- **Paging:** loop until a short page (`itertools.count(0, PAGE_ROWS)`), yield each page as a list.
- **Windows:** `max_days_per_run` bounds catch-up runs. `window_padding_days` covers publishers whose
  local dates cross UTC days.
- **Seed:** synthetic records in `ingest/seed/synthetic.py` for the seed week (deterministic, shaped
  like the API's records), served by `SeedPublishers.fetch_json`, which answers the request the source
  sends (NESO's SQL runs as sent, on DuckDB). Include a revision.
- **Tests:** unit tests for logic the seed doesn't reach (paging past a full page,
  `elt/tests/unit/test_neso.py`), plus a case in `test_ingest.py` that a revision closes the previous version.
- **Exception:** `merge` + `delete-insert` on `primary_key`, as Elexon does (no history, one row per key):
  dlt's `scd2` stores a record repeated within a load once per copy (ADR 0001). Only with evidence of
  such repeats, confirmed by the user.
