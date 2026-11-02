# Agent instructions

Power Desk: publisher data loaded by dlt into DuckDB, conformed by dbt, orchestrated by Dagster, shown on a
read-only dashboard. Start with [README.md](README.md) (layout, commands) and
[docs/architecture.md](docs/architecture.md) (layers, naming, rules).

## Querying the data

Query `marts`, then `ods` entities, joining `dims`. Never query `staging` or `raw`. Before writing SQL,
read the relation's data contract, `elt/contracts/<schema>/<relation>.odcs.yaml`. It gives the grain,
types, units, joins and the rules (`context.constraints`) that keep an answer correct
([data contracts](docs/data-contracts.md)).

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

- `onboard-source`: a new publisher or dataset, stage by stage, into marts
- `create-widget`: a dashboard card from a query that follows the contracts
- `verify-contract`: check a contract claim on the data, then ship it as dbt tests or amend it

## Checks

`make check` lints, then type-checks and tests the projects a change affects. While iterating, use
`make check-elt` or `uv run pytest elt/tests/unit`, and work on the seed week (`uv run power-desk-load-seed`).
