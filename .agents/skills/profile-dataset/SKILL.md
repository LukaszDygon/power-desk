---
name: profile-dataset
description: >-
  Gathers the evidence to design an ELT pipeline for a published dataset: the official
  documentation, real samples fetched from the publisher, and a profile of them after dlt's default
  normalization (keys, revisions, time steps, publication cadence and lag, nesting, volume per
  backfill horizon). Use in phase 2 of onboard-dataset, or whenever a design decision needs evidence
  from the data.
---

# Profile a Dataset

The outcome is `data/onboarding/<source>/profile/<table>/profile.md` plus the evidence section of
`scope.md`. Every fact used in the design must be checked against real data and the documentation.
If they disagree, record both.

## 1. Documentation first

From the publisher only (portal, API reference, data descriptions, code lists, terms of use):
- what a row is, each field's definition and unit, and the natural key the publisher states
- how the data is published: cadence, when revisions happen and how (in place, appended, re-exported
  files), how much history is offered, the time zone and resolution, and any DST behaviour
- the access route (API, file, push), authentication, rate limits and paging
- the code lists behind categorical fields (areas, technologies, units), and whether an existing mapping
  covers them (`elt/dbt/seeds/mappings/`, `dims` keys)

Cite each fact with a link plus its section or page. These citations become the catalogue
definitions (`catalog/definitions/<source>.yml`).

## 2. Fetch real samples (stratified)

Save the raw responses, unchanged, in `data/onboarding/<source>/samples/` using `curl -o`, or the
publisher's client for authenticated APIs. Fetch the smallest set that covers:
- **recent:** the last few days, a full publication cycle
- **oldest:** the first period on offer, to confirm the history and any change in format
- **a revision:** a period republished or corrected, if the documentation says revisions happen
- **a DST change** (the last Sunday of March or October), when the data is local-time or sub-daily
- **paging or limits:** one request at the publisher's maximum size

Time each fetch. Bytes per second and requests per day of data give the backfill estimates. Never
commit credentials, and keep the samples out of git (`data/` is ignored).

## 3. Profile

```bash
uv run power-desk-profile <source>__<dataset> data/onboarding/<source>/samples/<files> \
  [--records <path.to.rows>] --key <col,col> [--key ...] --time <col> --published <col> --available-from <date>
```

It loads the samples through dlt's default normalization, the same as the warehouse would, so the
nested fields come out as child tables. Then it reports per table: `SUMMARIZE` (types, nulls, distinct,
ranges); per candidate key: exact repeats and keys with several distinct rows; the value-time steps;
the publication cadence; the lag; and the volume per horizon. Column names are dlt's (snake_case). Run it
again with other `--key` candidates until one is unique per version. Query the profile's warehouse
(`profile.duckdb`) for anything else.

## 4. Derive the design (evidence -> decision)

| Evidence | Decision |
|---|---|
| Keys with several distinct rows; the documentation describes corrections | revised data: cursor on the publication/update time, `scd2` merged on the natural key |
| Whole reference file, no time column | snapshot: `scd2` without `merge_key` |
| Periodic files the publisher re-exports | file partitions |
| Child tables in the profile | keep them, joined in staging via `_dlt_parent_id` / `_dlt_list_idx` |
| Value-time step | native interval of the entity rows (`interval_minutes`) |
| Publication cadence and lag; the user's latency need | the ingest job (cron), the freshness preset, `max_days_per_run` |
| Codes in categorical fields | mappings to existing dimension keys; anything new is an exception |
| Volume per horizon, fetch timings | backfill options and `--chunk-days` |

Kinds and their dispositions: the `onboard-source` skill (`kinds/`). Fill the evidence and design
sections of `scope.md`. Mark every departure from the defaults in `onboard-dataset` as an exception.
