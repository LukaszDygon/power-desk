# ADR 0002: Data contracts exported from dbt, verified by dbt tests

- **Status:** accepted, 2026-11-02
- **Details:** [data contracts](../data-contracts.md)

## Context

The product is conformed data from many publishers that an analyst, or an AI turning a question into SQL,
can query without reading the models. The query has to know each relation's grain, units, keys and
joins, and the rules that keep an answer correct (one area level, one source, one time horizon). That
logic belongs with the data, not in marts or in prompts.

## Decision

- **Standard:** Open Data Contract Standard (Bitol), the latest release, v3.2.0. It is portable and
  widely supported, and v3.2.0 has what we need: `relationships` (foreign keys), a `timestamp` logical
  type, and `context` (RFC-0038) for guidance to AI agents. v3.0.1, considered first, had none of these.
- **Exported, not written:** contracts are generated from the dbt project. Descriptions and data tests
  come from the manifest, citations from the catalogue definitions, and types and units from the
  warehouse. Query guidance is written once, in dbt `meta`. The dbt project stays the single source of
  truth.
- **dbt verifies:** every key, required column, relationship and quality rule in a contract is a dbt
  data test, named in the contract (`engine: dbt`), and runs with every build. A claim without a test is
  not exported. We use no separate contract runner. datacontract-cli was tried; it adds about 20 packages
  and a second test engine, and under v3.0.1 it needed workarounds.
- **Amendable:** a contract states what the tests verify today. Tightening it means adding a test, and
  loosening it means relaxing or removing one. The `verify-contract` skill is the procedure.

## Consequences

- A model change shows up as a contract diff in review; the ELT integration tests fail while the
  committed contracts are stale or not valid ODCS.
- Tests stay cheap: they read only the rows of pending loads (load-id contract), and the nightly run
  checks everything.
- Contracts cover `marts`, `ods` and `dims`. Raw and staging stay internal.
- The contracts need a built warehouse to be regenerated, because the types come from it.

## Revisit when

- A consumer outside this repository needs the contracts: publish them (catalogue, OpenMetadata), and
  version them on breaking changes instead of with the dbt project.
- Checks need to run outside dbt (another engine, or a consumer verifying on its side).
