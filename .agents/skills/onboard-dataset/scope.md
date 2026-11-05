# Scope: <source>__<dataset>

<!-- Template (onboard-dataset skill). Every figure comes from profile.md or the publisher's
documentation, cited; delete these comments. -->

## Request

- Dataset, publisher page:
- What the user wants to answer:
- Latency and history needs; information the user gave:

## The data (evidence)

- Documentation: <links, with sections / pages>
- Samples fetched: <periods: recent, oldest, a revision, a DST day> (`samples/`)
- Contents: <what a row is, measures and units, codes>, profile: `profile.md`
- Natural key: <columns>, from <documentation reference>; profile: <duplicates, revisions>
- Time: <value time column, step>, published <cadence>, lag <median, p95>, runs ahead <how far into the future>
- Volume: <rows and MB per day>; available from <date>

## Design

| | Decision | Evidence |
|---|---|---|
| Kind | stream / revised stream / file partitions / snapshot | |
| Raw tables | `<source>__<dataset>` (+ child tables) | profile tables |
| Disposition, keys | `merge` + `scd2`, `merge_key` = <key>, `primary_key` = <key> | |
| Cursor | <column> | |
| Schedule | job `<name>` (`<cron>`), freshness `<preset>` | publication cadence |
| Entity | `ods_<entity>` (new / extended) | |
| Mart | `mart_<entity>` hourly; measures with unit and hourly aggregation | |
| Dimensions | existing keys and mappings (`seeds/mappings/...`); unmapped codes with row counts | code lists, reference data |
| Combined with | <other datasets in the same entity or compared with it, and why they are comparable> | |
| Contract rules | grain, constraints for querying | |

## Exceptions (need the user's confirmation)

- <none, or: what, why, cost>

## Backfill options

| Horizon | Days | Requests | MB downloaded | Rows stored | Load time | Basis |
|---|---|---|---|---|---|---|
| All history (default) | | | | | | measured / extrapolated from <what> |
| 1 year | | | | | | |
| 30 days | | | | | | |

## Shared with (parallel sessions only)

- <session, its worktree; the owner of each shared file; the agreed names, grain and keys>

## Open questions

- <what the evidence does not settle>

## Agreed (filled at the stop)

- Horizon:
- Exceptions:
- Answers:
