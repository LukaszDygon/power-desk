# ADR 0003: Onboarding defaults: versioned raw, time series, conformed dimensions

- **Status:** accepted, 2026-11-02; amended 2026-11-05 (scd2 for PVLive, no transformation, by reference)
- **Details:** [onboarding](../onboarding.md)

## Context

- New datasets should arrive quickly, through one evidence-based workflow, and look alike once loaded.
- Without stated defaults, every source becomes a design discussion, and losses (history, the time series)
  happen silently.

## Decision

Defaults for every new dataset; a departure is an exception the user confirms at the scope review.

- **Versioned raw:** `merge` + `scd2` on the natural key for every kind, except Elexon's streams.
- **Structured, as published:** dlt's child tables, no JSON columns, and no value changed at ingestion.
- **By reference:** a resource fetches only its own data and reads anything else from the warehouse.
- **Time series:** each dataset feeds an entity and its hourly mart, on the existing dimensions.
- **Schedule from evidence:** the publication cadence and the latency needed; a run takes at most a quarter
  of its interval.
- **All history**, unless the user picks a shorter backfill.
- **Evidence first:** design from real samples and the publisher's documentation; delivery ends with an
  acceptance run.

## Consequences

- **Raw grows** with each revision; staging reads the current versions.
- **Acceptance is reproducible:** `power-desk-accept` on a fresh warehouse, plus the `onboard-dataset` skill.
- **Parallel sessions,** each in its own git worktree.

## Appendix: Evidence and method

- **Versioned raw:** the data reads as it was at any time, and a reload of any window changes nothing
  (idempotent). Elexon's streams stay `delete-insert`: the API repeats records verbatim within a load, and
  dlt's `scd2` stores each copy ([ADR 0001](0001-keep-dlt-defaults-for-ingestion.md), amendment of
  2026-11-05).
- **Structured:** rows as published, nested data as dlt's child tables (default normalization). Ingestion
  makes no renames, drops or derived columns. Only unstructured data (e.g. an HTML table, GRIB) is parsed,
  by a data class (pydantic) that owns its parser and yields the values as published; derivations belong in
  staging.
- **By reference:** one resource per entity. A resource needing other data reads it from the warehouse
  (e.g. `dims.dim_site`), declared in `SourceSpec.references` so that it is built first.
- **Time series:** the entity is `ods_*`. Data that is not a time series, and new dimensions, are
  exceptions.
- **Schedule:** the publication cadence comes from profiling; the latency need comes from the user.
- **Consequences:** staging reads current versions with `_dlt_valid_to is null`. `power-desk-accept` decides
  the measurable criteria; the `onboard-dataset` skill adds the rest (conventions, contracts, docs).
