---
name: benchmark-pipeline
description: >-
  Chooses between pipeline designs by measurement when the fastest one is unclear: stratified,
  repeated acceptance runs of each variant (request size, paging, dlt parallelism, staging
  materialization), scored on ELT time plus analytical query time. Use while delivering a source
  (onboard-dataset phase 4), or when a source misses its schedule budget or a query is slow.
---

# Benchmark a Pipeline

Measure only when the answer isn't obvious and it matters, i.e. when it changes a scheduled run or a
backfill by more than a few seconds. Every variant must still meet the conventions (dlt's defaults,
ADR 0001), and the design of record stays the one that wins.

## 1. Variants: configuration, not forks

Express each variant as a setting the source already has, or gains for good: a constant in the
source's table of datasets (`DAYS_PER_REQUEST`, `PAGE_ROWS`, `BATCH_ROWS`), dlt configuration through
the environment (`EXTRACT__WORKERS`, `NORMALIZE__WORKERS`, `LOAD__WORKERS`, `DATA_WRITER__BUFFER_MAX_ITEMS`),
`parallelized=True` on resources, or a staging model's materialization (view vs incremental table).
Never keep two code paths: the losing variant is deleted.

## 2. Strata

Results depend on the window, so measure each variant on every stratum that matters:

| Stratum | Window | Stands for |
|---|---|---|
| scheduled | one scheduled run's worth (e.g. 1 day) | the cost every run pays (fixed overheads dominate) |
| catch-up | `max_days_per_run` | a capped run after downtime |
| backfill | a month or more of old data | throughput for the horizon the user chose |
| peak | a period with revisions or the densest data | the worst case |

## 3. Run

Run each variant × stratum at least 3 times, alternating variants (so the network and the cache affect
them alike). Label each run `<variant>/<stratum>`:

```bash
uv run power-desk-accept <source> --start-date <d> --end-date <d> --resources <tables> --label <variant>/<stratum>
```

Each run appends its timings to `data/onboarding/<source>/timings.jsonl`: ingest, repeat ingest, dbt
build, projected scheduled run, and per mart a daily aggregate query.

## 4. Compare

```bash
uv run python - <<'EOF'
import duckdb
print(duckdb.sql("""
    select label, count(*) as runs, median(ingest_s) as ingest, median(dbt_build_s) as dbt,
           median(projected_run_s) as projected, max(ingest_s) - min(ingest_s) as spread
    from read_json('data/onboarding/<source>/timings.jsonl') group by label order by label
"""))
EOF
```

Decide on the medians. A difference smaller than the spread is noise, so keep the simpler variant.
Weigh the scheduled stratum first (it runs every interval), then backfill throughput, then query time.
Record the result (variants, strata, medians, choice) in the source module's docstring or in `report.md`,
and delete the losing variants.
