# Acceptance report: <source>__<dataset>

<!-- Template (onboard-dataset skill); delete these comments. -->

## Summary

<one paragraph: what was delivered, against the agreed scope, and the verdict of the acceptance run>

## Acceptance criteria

| | Criterion | Evidence |
|---|---|---|
| | <the acceptance run's criteria, from acceptance/acceptance.md> | |
| | Scope delivered: every agreed item | <item: done / deviated> |
| | Conventions: the source is shaped like its nearest existing one; library features, not custom code | <files> |
| | Definitions cited from the publisher (catalogue) | <definitions file> |
| | Data contracts regenerated, every claim a dbt test | `git diff elt/contracts` |
| | Seed and integration test for the new raw tables | |
| | `make check` green | |

## Acceptance run

Window <start .. end>, <days> days, on the real publisher.

| | Seconds |
|---|---|
| Ingest / repeat ingest / dbt build | |
| Projected scheduled run (budget) | |
| Daily aggregate per mart | |

Profile of every relation with the source's rows: `acceptance/acceptance.md`. <the points worth reading:
nulls, ranges, how far into the future the data runs, coverage, unmapped codes; what it is combined with
and what any cross-check proves>

## Deviations from scope

- <none, or: what, why>

## Backfill

`uv run power-desk-backfill --sources <source> --start-date <d> --end-date <d> --chunk-days <n>`, about
<estimate> (acceptance ingest seconds per day times the horizon).

## Inspect the data

- Samples: `acceptance/sample/<relation>.csv`
- Dashboard on the acceptance warehouse: `POWER_DESK_DUCKDB_PATH=… POWER_DESK_DBT_MANIFEST=… uv run power-desk`

## Retrospective

- <what was slow or unclear in the workflow; which skill or script should change>
