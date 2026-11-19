# Data contracts

What a query may rely on for each queryable relation, and how those guarantees are made and changed.

## Contracts

- **One per relation:** every `marts`, `ods` and `dims` relation, in [ODCS v3.2.0](https://bitol-io.github.io/open-data-contract-standard/), at `elt/contracts/<schema>/<relation>.odcs.yaml`.
- **Content:** grain, types, units, keys, joins, quality rules and query rules.
- **Generated from dbt:** `catalog/contracts.py`; never edit them (Appendix B).
- **Why:** [ADR 0002](adr/0002-data-contracts-exported-from-dbt.md).

## Verifying

- **dbt tests only:** every test a contract names runs in each build (pending loads) and nightly (all rows).
- **Staleness:** ELT integration tests fail on a stale or invalid contract.

## Changing a contract

- **Change dbt, not the contract:** a test for a guarantee, `meta` context for an uncheckable query rule ([`verify-contract`](../.agents/skills/verify-contract/SKILL.md)).
- **Then rebuild and regenerate:** `uv run python -m power_desk_elt.catalog.contracts` (`--check` reports stale files).
- **Review:** the contract diff ships with the change.

## Query guidance

- **`context`:** `instructions` for reading the relation, `constraints` for what not to do.
- **Only facts:** about our pipeline, or rules from authoritative sources.
- **Testable rules become tests**, not context.

## Appendix B: Details

**Sources of each part.**

| Contract | Source |
|---|---|
| `description`, property descriptions | model and column descriptions (catalogue doc blocks) |
| `authoritativeDefinitions` | the official sources cited in `catalog/definitions` |
| `physicalType`, `logicalType`, property order | the warehouse |
| `customProperties` `unit`, `hourlyAggregation` | `dims.dim_metric`, else the column suffix (`_mw`, `_mwh`, `_pct`) |
| `primaryKey`, `dataGranularityDescription` | the model's uniqueness test (`*_unique_key`) |
| `required`, `unique` | `not_null` / `unique` tests of severity `error` |
| `relationships` | `relationships` tests |
| `quality` | every data test on the model, as `type: custom`, `engine: dbt`, its name as `implementation` |
| `context` (instructions, constraints) | dbt `meta`: the folder's `layer_context` (`dbt_project.yml`), then the model's `context` |

**Verification.** Nothing but dbt verifies contracts. The integration tests regenerate them from the seed
week and validate against `elt/contracts/odcs-json-schema-v3.2.0.json`.

**Changing.** Build the warehouse first (`power-desk-load-seed`, or `dbt build`), since generation reads it.

**Query guidance.** `context` is written for whoever turns a question into SQL (an analyst or an AI).
Typical constraints: don't mix area levels, sources or time horizons; don't read a missing hour as zero.
