# ADR 0002: Data contracts exported from dbt, verified by dbt tests

- **Status:** accepted, 2026-11-02
- **Details:** [data contracts](../data-contracts.md)

## Context

- Analysts, and AI agents writing SQL, query conformed data without reading the models.
- Each relation's grain, units, keys, joins and correctness rules belong with the data, not in marts or
  prompts.

## Decision

- **Standard:** ODCS (Bitol) v3.2.0, for its `relationships`, `timestamp` type and `context`.
- **Exported, not written:** generated from the dbt project, which stays the single source of truth.
- **dbt verifies:** every claim in a contract is a dbt test named in it; an untested claim is not exported.
- **Amendable:** a contract states what the tests verify today (`verify-contract` skill).

## Consequences

- **Review:** a model change shows as a contract diff, and stale contracts fail the ELT tests.
- **Cheap tests:** they read only pending loads; the nightly run checks everything.
- **Scope:** `marts`, `ods` and `dims`. Raw and staging stay internal.
- **Regenerating** contracts needs a built warehouse (it supplies the types).
- **Revisit when:** a consumer outside the repo needs the contracts, or checks must run outside dbt.

## Appendix: Evidence and method

- **Context:** the rules that keep an answer correct include using one area level, one source and one time
  horizon.
- **Standard:** v3.2.0 was the latest release. It adds `relationships` (foreign keys), a `timestamp`
  logical type and `context` (RFC-0038) for guidance to AI agents; it is portable and widely supported.
  v3.0.1, considered first, had none of these.
- **Sources of the export:** descriptions and data tests from the manifest, citations from the catalogue
  definitions, types and units from the warehouse. Query guidance is written once, in dbt `meta`. Each test
  is named in the contract with `engine: dbt` and runs with every build.
- **Amending:** tightening a contract means adding a test; loosening it means relaxing or removing one.
- **Contract failures:** the ELT integration tests fail while committed contracts are stale or not valid
  ODCS. Tests read only the rows of pending loads (load-id contract).
- **Alternative tried:** datacontract-cli. It adds about 20 packages and a second test engine, and under
  v3.0.1 it needed workarounds.
- **Revisit:** for outside consumers, publish the contracts (catalogue, OpenMetadata) and version them on
  breaking changes rather than with the dbt project. Checks outside dbt mean another engine, or a consumer
  verifying on its side.
