# Nested payloads (any kind)

Yield the records as published and let dlt's default normalization structure them. Never flatten
them by hand and never load JSON columns.

- **Nested objects** become columns `<field>__<subfield>`. **Lists** become child tables
  `<table>__<field>`, with `_dlt_parent_id` (the parent row's `_dlt_id`) and `_dlt_list_idx` (the
  position in the list). Under `scd2`, a parent's `_dlt_id` is its version, so each version has its own
  child rows.
- The profile (`power-desk-profile`) shows the tables dlt will create. The acceptance run fails on any
  JSON column.
- **Catalogue:** a child table needs a `tables` entry and definitions for its columns
  (`catalog/definitions/<source>.yml`), the same as a root table. `catalog.generate` declares it as a
  dbt source under its root resource's Dagster asset. It has no `_dlt_load_id`, so it has no freshness
  of its own (the root table's applies) and its tests are not scoped to pending loads.
- **Schedule:** nothing to add. One resource loads the root table and its children, and the root's
  `IngestJob` covers both.
- **Staging:** join the child to the current versions of its parent:
  `join {{ dlt_source(<source>, <table>) }} p on c._dlt_parent_id = p._dlt_id and p._dlt_valid_to is null`.
  Pending loads come from the parent's `_dlt_load_id`.
