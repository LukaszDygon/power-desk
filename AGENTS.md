# Agent instructions

Power Desk: publisher data loaded by dlt into DuckDB, conformed by dbt, orchestrated by Dagster, shown on a
read-only dashboard. Start with [README.md](README.md) (layout, commands) and
[docs/architecture.md](docs/architecture.md) (layers, naming, rules).

## Querying the data

Query `marts`, then `ods` entities, joining `dims`. Never query `staging` or `raw`. Before writing SQL,
read the relation's data contract, `elt/contracts/<schema>/<relation>.odcs.yaml`. It gives the grain,
types, units, joins and the rules (`context.constraints`) that keep an answer correct
([data contracts](docs/data-contracts.md)).

## Onboarding data

A request to add a dataset runs the `onboard-dataset` workflow ([onboarding](docs/onboarding.md)) in its own git
worktree (`claude -w onboard-<source>`, or EnterWorktree). Defaults: versioned raw (`scd2`), dlt's child tables
for nested data, a time series conformed to existing dimensions, a schedule from the publication cadence, and all
history ([ADR 0003](docs/adr/0003-onboarding-defaults.md)). Anything else is an exception for the user to confirm.
Stop for the user after the scope and after the acceptance run.

## Rules

- **Definitions are authoritative:** every description, classification or metric definition is quoted
  from an industry source (publisher, NESO, Elexon, DESNZ, ENTSO-E, EU law) and cited in
  `catalog/definitions`. Never write your own.
- **Generated files are never edited:** dbt sources and doc blocks (`catalog.generate`), data contracts
  (`catalog.contracts`), dlt schemas (`ingest/schemas/`). Change their inputs and regenerate.
- **Contracts ship with tests:** every claim in a contract is a dbt test; amend the contract instead of
  coding around it (`verify-contract` skill).
- **Ingestion keeps dlt's defaults** ([ADR 0001](docs/adr/0001-keep-dlt-defaults-for-ingestion.md)):
  yield rows as published. Ingestion time comes only from dlt's load metadata (`_dlt_load_id`).
- **Docs stay short:** summary level, no code-level detail. Decisions go into `docs/adr/`.
- **Projects meet through files:** `elt`, `dashboard` and `services` never import one another
  (`uv run lint-imports`).

## Skills (`.agents/skills/`)

- `onboard-dataset`: the onboarding workflow; drives the next three and `verify-contract`
- `profile-dataset`: documentation, real samples and their profile, the design they support
- `onboard-source`: the build, stage by stage, with a reference per pipeline kind (`kinds/`)
- `benchmark-pipeline`: stratified timing of design variants
- `create-widget`: a dashboard card from a query that follows the contracts
- `verify-contract`: check a contract claim on the data, then ship it as dbt tests or amend it

## Checks

`make check` lints, then type-checks and tests what a change affects (up to about 5 minutes). While
iterating, use `uv run pytest elt/tests/unit` and `make format`, and work on the seed week
(`uv run power-desk-load-seed`; add `--fresh` after raw columns change). Run `make check` once, at the end,
in the background. Pipe its output only with `set -o pipefail`. A passing run on a clean tree is recorded,
and the pre-push hook then skips that tree. A dbt exit code of -11 is a DuckDB crash, not noise: compare
several runs with and without your change.

## Failing checks and runs

Find them in `elt/dbt/target/run_results.json` (or the run's own target), `test_failures.<test>` in the
warehouse, a backfill's log, or the Dagster run. Classify each before fixing:
- **orchestration:** what ran or was tested; fix the scope, not the test
- **the publisher's data:** `verify-contract`
- **our mapping or model:** fix it, and find out who defines the codes before deciding

## Git and worktrees

- One session per worktree. New work, fixes included, gets its own worktree from `origin/main`, never
  another session's branch. Never enter a worktree you didn't create; a `locked` one is in use.
- Never `git stash` (it is shared by all worktrees), and never amend a commit; add one.
- Before pushing `main`: `git fetch`, merge `origin/main`, then renumber clashing ADRs (`make lint`
  checks) and regenerate generated files instead of merging them. The pre-push hook fails at once if
  `main` moved.
