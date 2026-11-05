---
name: onboard-dataset
description: >-
  End-to-end workflow for adding a published dataset to the warehouse at the user's request:
  profile real data and documentation, propose a scope for the user to review (backfill horizon
  included), deliver the full ELT pipeline, then run and report an acceptance run with a data
  sample for the user to accept or revise. Use when the user asks for a dataset, feed or
  publisher to be added; it drives the profile-dataset, onboard-source, verify-contract and
  benchmark-pipeline skills.
---

# Onboard a Dataset

Five phases, with two stops for the user: after the scope (phase 3) and after the acceptance run
(phase 5). Never skip a stop. Artefacts go in `data/onboarding/<source>/` (gitignored): `samples/`,
`profile/<table>/profile.md`, `scope.md`, `acceptance/`, `timings.jsonl`, `report.md`.

## 0. Own worktree

Every onboarding runs in its own git worktree, so parallel sessions never share code, warehouse or
dlt state. Do this first, even when the session started from `onboard-source`.
- Check: `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`. If it doesn't, you're in
  the main checkout: create one with EnterWorktree, or ask the user to start the session with
  `claude -w <name>`. Name it `onboard-<source>`, or `onboard-<source>-<dataset>` when `git worktree list`
  already shows one for the source (then read "Parallel sessions" below).
- Never enter or edit a worktree you didn't create. A `locked` worktree belongs to a live session.
- Then run `uv sync` and `uv run power-desk-load-seed --fresh` (the dev warehouse from the seed week, about a
  minute). Check that `.env` is present (Claude Code copies it into worktrees, see `.worktreeinclude`).
  If it's missing, ask the user for the credentials the publisher needs, and never print them.
- Everything below stays in this worktree: its own `data/` (warehouses, onboarding artefacts) and
  `.dlt/`. Commit to the worktree's branch, and push or merge only when the user asks. Never `git stash`
  (all worktrees share the stash list); commit work in progress instead.
- The worktree's sandbox refuses compound shell commands (heredocs, `$(...)`, `sed -i`, `xargs`): edit
  files with Edit/Write, and put probes in scripts under `data/onboarding/<source>/scratch/`, never in
  `samples/`.

## Parallel sessions

Two sessions on related datasets (one publisher, a shared dimension or macro) agree on these at the
start, through SendMessage, and record them in both `scope.md` files ("Shared with"):
- **One owner per shared file** (a source module, a macro, a dimension). The other session reads the owner's
  commits only, never its uncommitted files.
- **Commit the shared skeleton early.** Once its stage checks pass, the owner asks its user for an early
  commit to its branch, and the other session merges that branch. Waiting for acceptance stalled a
  session for 20 hours.
- **Names and grain** (raw tables, `source_dataset` codes, staging keys, the interval convention) are in
  `scope.md`, not only in messages.
- **Review each other's diff** before stop 2. In the ECMWF sessions, this found five real bugs.

## 1. Intake

Record the request in `scope.md` (template: [scope.md](scope.md)): the dataset, the publisher's page,
what the user wants to answer with it, any latency or history needs, and any extra information they
gave. Ask only what you can't find out yourself (usually nothing yet).

## 2. Profile and design (`profile-dataset` skill)

Fetch real data and the official documentation, profile them (`uv run power-desk-profile`), and derive
every design decision from that evidence. The defaults, from which any departure is an **exception**
needing the user's confirmation:

| Decision | Default | Exception (confirm with the user) |
|---|---|---|
| History | raw keeps every version: `scd2`, so the data can be read as it was at any time | `delete-insert` (no time travel), e.g. a huge stream the publisher never revises |
| Idempotency | a reload of any window changes nothing; the natural key comes from the documentation | none: always required |
| Structure | rows as published; nested data in dlt's child tables (`<table>__<field>`) | JSON columns |
| Transformation | a time series: entity (`ods_*`) and hourly mart, conformed to existing dimensions | not a time series; a new dimension |
| Schedule | from the publication cadence (profile) and the user's latency need: an existing `IngestJob` with that cadence, or a new one | a schedule faster than the publisher updates |
| Backfill | all history the publisher offers | a shorter horizon (the user chooses at the stop) |

## 3. Stop: scope review

Finish `scope.md`. Every figure in it comes from the profile or the documentation, cited. Then show
the user a short summary and ask (AskUserQuestion in Claude Code):
- **Backfill horizon:** all history (the default), or one of the shorter horizons. For each, give the
  requests, the MB downloaded, the rows stored and the load time, each marked *measured* or *extrapolated
  from <what>*. Download and storage differ whenever ingestion reduces the data (byte ranges, points
  of a grid).
- **Exceptions:** each one, with the reason and its cost (e.g. "no time travel: one row per key").
- **Anything the evidence leaves open:** an ambiguous key, units, or codes without a mapping. List every
  unmapped code with its row count.
- **Combinations:** a dataset joined or compared with another (same entity, or an "actual" against a
  forecast). Say what each is and why they are comparable.

Don't build anything until the user has answered. Record the answers in `scope.md`.

## 4. Deliver

Build with the `onboard-source` skill, stage by stage. It has one reference per pipeline kind
(`kinds/`). Keep to the repository's conventions: a source is a table of datasets plus small fetch
functions, shaped like its nearest existing source. Use the library feature (dlt, DuckDB, dbt) before
writing your own code, and configuration over code paths. Use the minimum code that keeps every source
alike.
- Contracts: the marts' and entities' tests and query rules (`verify-contract` skill), regenerated with
  `uv run python -m power_desk_elt.catalog.contracts`.
- Speed: where the fastest design isn't obvious (request size, paging, parallelism, materialization),
  measure it with the `benchmark-pipeline` skill. Judge by ELT time plus analytical query time.
- Acceptance run, on the real publisher, for a window covering at least one full publication cycle and
  any DST change in range (for example the last 7 days):

  ```bash
  uv run power-desk-accept <source> --start-date <d> --end-date <d> --resources <the new raw tables>
  ```

  It builds a fresh warehouse (`data/onboarding/<source>/acceptance/`) and checks loading, structure,
  idempotency, time travel, logging, dbt tests, dimension registration, time series, schedule budget
  and query time. Fix and re-run until every criterion passes or is a confirmed exception.
- Check order, cheapest first:
  - while building: each stage's check, `uv run pytest elt/tests/unit`, `make format`
  - once the build passes: the acceptance run, with `make check` in the background next to it (up to about 5 min)
  - pipe a check's output only with `set -o pipefail`, or a failure passes for success
- `make check` green (the contracts, integration and coverage tests included). A dbt exit code of -11 is a
  DuckDB crash. Treat it as a finding: compare several runs with and without your change.

## 5. Stop: acceptance report

Write `report.md` from [report.md](report.md), retrospective included, before you ask anything. Then give
the user its summary. It holds:
- the acceptance criteria: those decided by the acceptance run (`acceptance.md`) and the rest
  (conventions, contracts, docs, `make check`), each with its evidence
- the profile of the acceptance run: rows, time span (including how far into the future the data
  runs) and the columns of every relation holding the source's rows
- deviations from the agreed scope, with the reasons
- the backfill: the exact command for the chosen horizon and its estimated duration (acceptance
  throughput times the horizon)
- how to inspect the data: the CSV samples in `acceptance/sample/`, or the dashboard on the acceptance
  warehouse:
  `POWER_DESK_DUCKDB_PATH=data/onboarding/<source>/acceptance/warehouse.duckdb POWER_DESK_DBT_MANIFEST=data/onboarding/<source>/acceptance/target/manifest.json uv run power-desk`

Then ask: accept, or revise (and what). If they want revisions, loop back to the phase they touch. When
they accept, commit to the worktree's branch.

## After acceptance (when the user asks)

- **Backfill:** the command in `report.md`. It tests only what it loaded.
- **Merge into `main`:**
  - `git fetch` and `git merge origin/main` into the worktree's branch.
  - Renumber any new ADR whose number `main` already has (`make lint` fails on duplicates).
  - Regenerate generated files rather than resolving their conflicts by hand.
  - `make check` passes, and records the tree.
  - Push. The pre-push hook skips a tree that already passed, and fails at once if `main` moved meanwhile.
- **Leave the worktree:** call ExitWorktree, and tell the user to `git pull` in the main checkout
  (the worktree's branch has no upstream).

## Retrospective

End `report.md` with a few lines on the workflow itself: what was slow or unclear, what the evidence
couldn't settle, and which skill or script should change. These notes are how the workflow improves
between sessions.
