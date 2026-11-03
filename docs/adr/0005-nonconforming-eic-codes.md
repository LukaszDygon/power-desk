# ADR 0005: Nonconforming EIC codes in a reviewed seed, beside ENTSO-E's registry

- **Status:** accepted, 2026-11-03
- **Details:** [architecture](../architecture.md) (Dimensions)

## Context

Elexon publishes `10YGB----------B` as the bidding zone of some REMIT messages, for interconnectors and GB
units whose other messages carry `10YGB----------A` (GB). No issuing office allocated it: its prefix
names ENTSO-E, which registers every code it issues, and its check character is invalid, which the EIC
Reference Manual (5.5, sections 3.2.4 and 5.3) rules out for local codes too. Left unresolved, its rows
fall out of any GB query that joins `dim_area` (about 3% of GB generation unavailability).

## Decision

- **A reviewed seed:** `seeds/dims/nonconforming_eic_codes.csv` lists each accepted code with the
  registered code it stands for, the dataset that uses it, the rules it breaks and the evidence.
- **Kept separate, unioned in the dimension:** ENTSO-E's registry is loaded as published. `dim_eic_code`
  adds each seeded code with the attributes and versions of its registered code, and no issuing office;
  `registered_eic_code` (`dim_area.registered_area_eic_code`) tells the two apart.
- **Rolled up through the registered code:** `bridge_area_hierarchy` gives a nonconforming area its
  registered area and that area's ancestors, one level deeper, so roll-ups reach it. This is done after the
  recursive closure, not as a link inside it: a link there made DuckDB 1.5.4 (dbt's engine) crash
  intermittently in the recursive CTE's join filter.
- **Facts keep the published code:** entities and marts carry the code as published; queries resolve it
  through the dimension.

## Consequences

- Area counts must use `registered_area_eic_code`; a nonconforming code repeats its registered area's
  roles (the `dim_area` contract says so).
- A new nonconforming code still warns (`*_known_area`) until it is reviewed and seeded.
