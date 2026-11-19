# ADR 0006: Gridded forecasts load as values at named points

- **Status:** accepted, 2026-11-02 (ECMWF onboarding scope review); amended 2026-11-05 (points by reference)
- **Details:** [architecture](../architecture.md#ingestion); evidence in the ECMWF onboarding (`scope.md`)

## Context

- ECMWF open data is global GRIB2 grids: about 2.2 billion values a day for the eight fields needed, too
  many to load as rows.
- The portal's index files give each field's byte range, so single fields can be fetched.

## Decision

- **Named points only:** keep the values at the grid points nearest the selected REPD sites, without
  interpolation.
- **One row per field and point,** with the GRIB keys as published.
- **Points by reference:** the source reads the selected sites from `dims.dim_site`, which is built first.
- **One parser:** GRIB is decoded only through a data class (`GridValue`, using eccodes).
- **In dbt:** accumulated fields are differenced in staging, and units are converted in the entity by
  parameter id.

## Consequences

- **Volume:** about 113k rows a day instead of billions; a run loads in 1-6 minutes.
- **New sites** get weather from the next run after `dim_site` lists them; there is no backfill.
- **Other points or areas** need a new decision, since the GRIB files are not kept.
- **Readers** need no spatial extension.

## Appendix: Evidence and method

- **Volume:** each field is a 0.25° global grid of 1,038,240 points. Eight surface fields over four daily
  runs come to about 2.2 billion values a day, so rows as published
  ([ADR 0001](0001-keep-dlt-defaults-for-ingestion.md)) cannot be loaded. A single field is about 4.5 MB
  per step.
- **Points:** the grid points ecCodes finds nearest to the REPD's operational wind and solar sites of at
  least 50 MW: 115 sites, 83 grid points. A row carries the point's latitude and longitude, and dlt names,
  types and hashes it as for any source.
- **By reference:** the source reads the selected sites' latitude and longitude from `dims.dim_site`
  (`is_selected`) through its pipeline's destination. The site rule (dbt vars) and the conversion from
  British National Grid (DuckDB's spatial extension) exist only in dbt. The orchestrator builds `dim_site`
  before the ECMWF assets (an asset dependency), as do the seed load and the acceptance run
  (`SourceSpec.references`). While `dim_site` is not built, a run reads no points.
- **Parsing:** `GridValue` keeps the keys and values as eccodes reads them. Units are converted by the
  ECMWF Parameter Database's parameter id, never by short name.
- **Measured:** about 113k rows a day (00z and 12z); a run loads in 1-6 minutes, depending on the portal's
  response (acceptance run, 2026-11-02).
- **No backfill:** the portal keeps about 12 runs, and no backfill path exists, so earlier runs are not
  re-read for a new site.
- **Spatial:** `dim_site` is a table, so readers need no spatial extension; dbt loads the extension
  (`profiles.yml`).
