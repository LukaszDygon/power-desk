# ADR 0006: Gridded forecasts load as values at named points

- **Status:** accepted, 2026-11-02 (ECMWF onboarding scope review)
- **Details:** [architecture](../architecture.md#ingestion); evidence in the ECMWF onboarding (`scope.md`)

## Context

ECMWF open data is GRIB2: each field is a global grid (0.25°: 1,038,240 points). The eight surface
fields an energy desk needs come to about 2.2 billion values a day across the four daily runs, so rows
as published ([ADR 0001](0001-keep-dlt-defaults-for-ingestion.md)) cannot be loaded. The portal's
index files give each field's byte range, so single fields can be fetched (about 4.5 MB per step).

## Decision

- Ingestion decodes the GRIB fields it needs (eccodes, ECMWF's library) and keeps the values at named
  points only: the grid points ecCodes finds nearest to the REPD's operational wind and solar sites of
  at least 50 MW (115 sites, 83 grid points). Values are not interpolated.
- A row is one field at one grid point, with the field's GRIB keys as published and the point's
  latitude and longitude; dlt names, types and hashes it as for any source.
- Site coordinates (British National Grid) convert to latitude and longitude with DuckDB's spatial
  extension, both at ingest and in `dim_site`, so the two agree. The site rule is kept in the source
  and as dbt vars, held equal by a unit test.
- Accumulated fields are differenced per run in staging; units are converted in the entity by
  parameter id (ECMWF Parameter Database), never by short name.

## Consequences

- About 113k rows a day (00z and 12z), instead of billions; a run loads in 1-6 minutes, depending on the
  portal's response (acceptance run, 2026-11-02).
- A site added to the REPD gets weather from its first run after the extract that lists it; earlier
  runs are not re-read (the portal keeps about 12 runs, and no backfill path exists).
- Area means, other points or a full grid need a new decision: the GRIB files are not kept.
- `dim_site` is a table, so readers need no spatial extension; dbt loads it (`profiles.yml`).
