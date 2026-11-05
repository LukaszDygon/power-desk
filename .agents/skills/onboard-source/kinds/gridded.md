# Kind: gridded forecast runs (fields on a global grid, one run at a time)

**Model:** `ingest/sources/ecmwf.py` (IFS and AIFS), staging macro `macros/ecmwf.sql`, ADR 0006.

- **Scope decision:** a global grid is billions of values a day, so rows as published can't be loaded.
  Which points (named sites, area means) and which fields is a scope decision for the user, not a default.
  The ECMWF rule: grid points nearest to the REPD's operational wind and solar sites, not interpolated.
- **Fetch:** only the fields needed, by byte range from the publisher's index files (one request per field
  and step), decoded with the publisher's library (eccodes for GRIB). Keep the GRIB keys as published, plus
  the point's latitude and longitude. The files are not kept.
- **Stream of runs:** the cursor is the run date; read a run once it is complete (its last step
  published); every key holds the run time; `merge` + `scd2` on the natural key, so a run loaded again
  changes nothing. The portal keeps only recent runs, so check mirrors and archives (e.g. cloud open-data
  buckets) before stating the history on offer.
- **Points shared with a dimension:** the ingest selects points from the same reference data and rule
  that the dimension (`dim_site`) uses. Hold the two equal with a unit test, and compare trimmed values on
  both sides.
- **Staging:** rebuild a run whole, so each step finds its neighbours. Instantaneous fields describe the
  interval to the next step, and accumulated fields the difference from the previous step, so both cover
  the same interval. Convert units by parameter id, never by short name: models reuse short names for
  different parameters (IFS and AIFS `tcc`).
- **Precision:** GRIB packs each field to a step that depends on its range. State it per value
  (`packing_uncertainty`) instead of assuming fixed bounds.
- **Keys:** the incremental `unique_key` in staging is raw's row-level natural key. A run-level key was
  measured at 383 s against 0.9 s (`onboard-source`, Pitfalls).
- **Seed:** synthetic GRIB2 step files over a small grid (`synthetic.ecmwf_step_file`), served by
  `SeedPublishers` with their index and byte ranges. Add a unit test against the real HTTP client for a run
  that isn't published yet (404, `test_ecmwf.py`), because the replay doesn't exercise it.
