# Onboarding a dataset

Ask the agent for a dataset ("add <dataset> from <publisher>"), ideally in a new worktree:
`claude -w onboard-<source>`. The [`onboard-dataset`](../.agents/skills/onboard-dataset/SKILL.md) skill
runs the workflow, and the defaults it applies are in [ADR 0003](adr/0003-onboarding-defaults.md).

| Phase | Agent | You |
|---|---|---|
| 1. Intake | records the request | name the dataset; add what you know (use, latency, history) |
| 2. Profile and design | fetches documentation and real samples, profiles them (`power-desk-profile`) | |
| 3. Scope review | proposes the design with the evidence, the backfill options and any exceptions | choose the horizon (default: all history), confirm exceptions |
| 4. Deliver | builds the pipeline, contracts and tests; benchmarks where unclear; runs an acceptance run of the new datasets (`power-desk-accept --resources`) | |
| 5. Acceptance | reports criteria, profile, deviations and the backfill command | inspect the sample; accept or ask for revisions; ask for the backfill and the merge |

## Artefacts

Everything for a source lives in `data/onboarding/<source>/` in the worktree (not committed):
`samples/` (raw responses), `profile/<table>/profile.md`, `scope.md`, `acceptance/` (warehouse,
`acceptance.md`, `sample/*.csv`, `accept.log`), `timings.jsonl` (all acceptance runs) and `report.md`.

To inspect the accepted data on the dashboard, point it at the acceptance warehouse:

```bash
POWER_DESK_DUCKDB_PATH=data/onboarding/<source>/acceptance/warehouse.duckdb \
POWER_DESK_DBT_MANIFEST=data/onboarding/<source>/acceptance/target/manifest.json uv run power-desk
```

## Skills and scripts

| | Purpose |
|---|---|
| `onboard-dataset` | the workflow and its two stops for the user |
| `profile-dataset` | documentation, stratified samples, profile, design from evidence |
| `onboard-source` | the build, stage by stage, with a reference per pipeline kind (`kinds/`) |
| `verify-contract` | data contracts and the dbt tests behind them |
| `benchmark-pipeline` | stratified timing of variants when the fastest design is unclear |
| `power-desk-profile` | samples through dlt's normalization into DuckDB, then keys, revisions, cadence, lag and volume |
| `power-desk-accept` | real data through the whole ELT into a fresh warehouse, with criteria, timings, profile and samples |

Each report ends with a retrospective on the workflow itself. Use those notes to improve the skills
between sessions.

## Parallel sessions

Each session gets its own worktree (`onboard-<source>-<dataset>` when the source already has one). Sessions
on related datasets agree on an owner for each shared file and record the shared names and grain in their
`scope.md`. The owner commits the shared code early, so the other session can merge it, and each reviews
the other's diff before acceptance. Merge `main` in before merging back: the seeds that every onboarding
appends to merge by union (`.gitattributes`), and `make lint` fails on duplicate ADR numbers.
