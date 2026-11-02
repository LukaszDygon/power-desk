# ADR 0003: Onboarding defaults: versioned raw, time series, conformed dimensions

- **Status:** accepted, 2026-11-02
- **Details:** [onboarding](../onboarding.md)

## Context

New datasets should arrive quickly and consistently, each through the same evidence-based workflow,
and look alike once loaded. Without stated defaults, every source becomes a new design discussion,
and choices like dropping history or skipping the time series get made silently.

## Decision

A new dataset is onboarded with these defaults. A departure is an exception that the user confirms at
the scope review:

- **Versioned raw:** `merge` + `scd2` for every kind (streams included), merged on the natural key,
  so the data can be read as it was at any time. A reload of any window changes nothing (idempotent).
  The `delete-insert` streams already loaded (Elexon, PVLive; ADR 0001) stay as they are.
- **Structured:** rows as published, nested data as dlt's child tables (default normalization), no
  JSON columns.
- **Time series:** each dataset feeds an entity (`ods_*`) and its hourly mart, conformed to the
  existing dimensions. Data that is not a time series, and new dimensions, are exceptions.
- **Schedule from evidence:** the publication cadence (profiled) and the user's latency need. A
  scheduled run takes at most a quarter of its interval.
- **All history** unless the user picks a shorter backfill horizon.
- **Evidence first:** design decisions come from real samples and the publisher's documentation, and
  delivery ends with an acceptance run on the real publisher, reported to the user.

## Consequences

- Raw grows with each revision, and staging reads the current versions (`_dlt_valid_to is null`).
- Acceptance is reproducible: `power-desk-accept` builds a fresh warehouse and decides the measurable
  criteria. The `onboard-dataset` skill adds the rest (conventions, contracts, docs).
- Sessions run in separate git worktrees, so several onboardings can proceed at once.
