# ADR 0005: Nonconforming EIC codes in a reviewed seed, beside ENTSO-E's registry

- **Status:** accepted, 2026-11-03
- **Details:** [architecture](../architecture.md) (Dimensions)

## Context

- Elexon uses `10YGB----------B`, which no issuing office allocated, as GB's zone in some REMIT messages.
- Left unresolved, those rows drop out of GB queries (about 3% of GB unavailability).

## Decision

- **A reviewed seed:** `seeds/dims/nonconforming_eic_codes.csv` lists each accepted code with the
  registered code it stands for.
- **Unioned in the dimension:** the registry stays as published; `dim_eic_code` adds each seeded code and
  marks it with `registered_eic_code`.
- **Rolled up through the registered code:** this happens in `bridge_area_hierarchy`, after the recursive
  closure.
- **Facts keep the published code:** queries resolve it through the dimension.

## Consequences

- **Counting areas** must use `registered_area_eic_code`.
- **A new nonconforming code** warns (`*_known_area`) until it is reviewed and seeded.

## Appendix: Evidence and method

- **Usage:** Elexon publishes `10YGB----------B` for interconnectors and GB units whose other messages
  carry `10YGB----------A` (GB).
- **Why it is nonconforming:** its prefix names ENTSO-E, which registers every code it issues, and its check
  character is invalid, which the EIC Reference Manual (5.5, sections 3.2.4 and 5.3) also rules out for
  local codes. Its rows would fall out of any GB query that joins `dim_area`.
- **Seed columns:** the code, the registered code, the dataset that uses it, the rules it breaks, and the
  evidence.
- **Dimension:** a seeded code takes the attributes and versions of its registered code, with no issuing
  office. `registered_eic_code` appears as `dim_area.registered_area_eic_code`. A nonconforming code
  repeats its registered area's roles, which the `dim_area` contract states.
- **Roll-up:** the bridge gives a nonconforming area its registered area and that area's ancestors, one
  level deeper. It is not a link inside the recursive closure: there, it made DuckDB 1.5.4 (dbt's engine)
  crash intermittently in the recursive CTE's join filter.
