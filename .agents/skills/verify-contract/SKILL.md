---
name: verify-contract
description: >-
  Checks a data contract claim (grain, keys, required columns, allowed values, ranges,
  relationships, completeness, a query rule) against the data, then ships it as dbt data tests,
  or amends the contract where the data or the publisher makes the claim impractical. Use when a
  query or widget needs a guarantee, a contract test fails, or a model change alters a contract.
---

# Verify a Data Contract

Contracts (`elt/contracts/<schema>/<relation>.odcs.yaml`) are exported from the dbt project, and
dbt tests are what verify them ([data contracts](../../../docs/data-contracts.md)). A contract only states
what its tests check today. So a claim is shipped as a test, or turned into a query rule, or dropped.
Work on the smallest data that answers the question: the seed week, one model, one query.

## 1. State the claim

Read the relation's contract: its `properties`, `quality`, `relationships` and `context`. Write the
claim as one predicate on rows or keys, for example "one row per `timestamp_utc`, `_series_key`",
"`price_per_mwh` is never null", or "every `area_eic_code` is in `dim_area`". The meaning of a
measure, unit or classification comes from an authoritative source (publisher, NESO, Elexon, ENTSO-E,
EU law). Never make one up.

## 2. Check the data first (seconds)

Count the violations with one read-only query on the dev warehouse (`uv run power-desk-load-seed` builds it
from the seed week) before writing any test:

```bash
uv run python -c "import power_desk_warehouse as w
with w.connect() as c: print(c.sql(\"select source_dataset, count(*) from marts.<relation> where not (<predicate>) group by all\"))"
```

Group by `source_dataset` and `source_code`, so you can see which feed breaks the rule.

## 3. Decide, pragmatically

| Finding | Do |
|---|---|
| No violations | Ship the test (step 4) |
| Our bug (a join fans out, a mapping is missing) | Fix the model or the mapping seed, then ship the test |
| The publisher's reality (late, gappy, revised, unmapped codes) | Ship it at `severity: warn`, or narrow it with `where:`; say why in the test's name or the column's description |
| A code that isn't in its registry, or doesn't conform to it (e.g. an EIC code ENTSO-E doesn't list) | Research the issuing body's rules first (issuing offices, check characters). If the code is in genuine use, add it to a reviewed seed beside the registry (`nonconforming_eic_codes`, ADR 0005), cited, rather than a query rule |
| A rule about how to query, not a property of rows | Write it as `context` (step 5), not as a test |
| Too costly or not needed by any consumer | Leave it out; the contract stays smaller |

Amending is normal: relaxing or removing a test is a contract change, reviewed as a diff, not a failure.

## 4. Ship the dbt test, cheaply

- Prefer the existing generic tests: `not_null`, `dlt_unique` (key-scoped uniqueness; use it over
  `unique` for composite keys), `relationships`, `accepted_values`, `expression_is_true` (one row-level
  predicate), `no_missing_intervals`, `no_missing_settlement_periods` (`elt/dbt/tests/generic/`). Add a
  generic only for a rule several models need.
- Tests read only the rows of pending loads (`macros/dlt/test_scope.sql`), so they stay cheap in
  scheduled runs. Keep them row-level, so that scoping applies. Use `config: meta: dlt_unscoped: true` only
  for a test that must see the whole table, and accept its cost.
- Name it `<model>_<rule>` (e.g. `mart_energy_price_known_area`): its failures are stored in
  `test_failures.<name>`, and the contract cites the name.
- Run only that model and its tests, over every row (seconds on the seed week). Without
  `dlt_scope: all`, nothing is pending and the tests see no rows:

```bash
uv run dbt build --project-dir elt/dbt --profiles-dir elt/dbt --select <model> --vars '{"dlt_scope": "all"}'
```

## 5. Query rules (`context`)

Add the rule to the model's `config.meta.context` (`instructions`, `constraints`) in its `.yml`. A rule
shared by a folder goes in `+meta.layer_context` in `dbt_project.yml`. Constraints are negative
guidance ("Do not sum across area levels..."), written for someone turning a question into SQL. Include only
facts about our pipeline or rules from an authoritative source, and cite the source in the column's catalogue
definition.

## 6. Regenerate and check

```bash
uv run python -m power_desk_elt.catalog.contracts      # after the dbt build; --check lists stale contracts
git diff elt/contracts                                  # the contract change, for review
make check-elt                                          # includes: contracts current and valid ODCS
```
