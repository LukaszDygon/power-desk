# Data contracts

Every queryable relation (`marts`, `ods`, `dims`) has a data contract in
[ODCS v3.2.0](https://bitol-io.github.io/open-data-contract-standard/), in
`elt/contracts/<schema>/<relation>.odcs.yaml`. A contract is what a query may rely on: grain, column
types, units, keys, joins, quality rules, and the rules for querying the relation correctly. Why we
work this way: [ADR 0002](adr/0002-data-contracts-exported-from-dbt.md).

## Where each part comes from

Contracts are generated (`catalog/contracts.py`); never edit them.

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

## Verifying

dbt runs every test a contract names, in each build (scoped to pending loads) and nightly (unscoped).
Nothing else verifies contracts. The ELT integration tests regenerate them from the seed week and
fail while a committed contract is stale or not valid ODCS (schema: `elt/contracts/odcs-json-schema-v3.2.0.json`).

## Changing a contract

1. Change the dbt project: a test (to add or relax a guarantee), or `meta` context (a query rule that
   no test can check). Procedure: the [`verify-contract`](../.agents/skills/verify-contract/SKILL.md)
   skill.
2. Build the warehouse (`power-desk-load-seed`, or `dbt build`), then regenerate:
   `uv run python -m power_desk_elt.catalog.contracts` (`--check` reports stale files).
3. Review the contract diff with the change.

## Query guidance

`context` is written for whoever turns a question into SQL (an analyst or an AI): `instructions` say
how to read the relation, and `constraints` say what not to do (mix area levels, sources or time
horizons, read a missing hour as zero). Only facts about our pipeline or rules from authoritative
sources go there. A rule that can be checked on the data becomes a test instead.
