# ADR 0001: Keep dlt's default row handling for ingestion

- **Status:** accepted, 2026-10-28; amended 2026-10-28 (streams: `upsert` -> `delete-insert`), 2026-11-05
  (PVLive: `scd2`; Elexon stays `delete-insert`)
- **Evidence:** [ingestion study](evidence/0001-ingestion-study.md)

## Context

- Sources yield row dicts; dlt types, names and hashes them and loads Parquet into DuckDB
  ([write dispositions](../architecture.md#appendix-b-details)).
- 144 measured runs on a real ENTSO-E month, plus small-load, mart-history and failure cases, found designs
  up to 10x faster.

## Decision

- **dlt's defaults:** row dicts, with dlt inferring types, normalizing names and computing row ids.
- **Merge strategies unchanged:** `scd2` by default; Elexon streams `delete-insert` on the natural key.
- **One non-default setting:** Parquet load files.
- **Why:** every resource is written the same way for any source or destination, with no Arrow plumbing and
  no hashing or version columns of our own.

## Consequences

- **Cost:** about 21-23 s per ENTSO-E month (mostly normalize), with peak memory under 900 MB.
- **Known risks:** out-of-order replays, duplicates after a mid-load kill, a lost dataset, lock retries, and
  Postgres `work_mem`. Each has a mitigation (appendix).
- **Faster avenues measured:** Arrow batches (2-3 s a month), `delete-insert` on key + `UpdateTime`, and
  DuckLake (appendix).
- **Revisit when:**
  - ingestion time matters (multi-year backfills);
  - the destination is Delta, Iceberg or Postgres;
  - duplicates or replays show up;
  - dlt hashes Arrow rows.

## Appendix: Evidence and method

The method, the search space, the results, the risks with their mitigations, the ranked avenues and the
amendments' evidence are in the [ingestion study](evidence/0001-ingestion-study.md).
