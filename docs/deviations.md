# Deviations

Every place the code departs from the [architecture](architecture.md); remove an entry when its departure goes, add one only with the user's agreement.

- **Elexon streams (`bmrs`, except REMIT):** `delete-insert`, not `scd2`, so no time travel ([ADR 0001](adr/0001-keep-dlt-defaults-for-ingestion.md)).
- **ECMWF forecast runs:** raw keeps named fields at points near selected sites, not the grid ([ADR 0006](adr/0006-gridded-forecasts-at-named-points.md)).
- **NESO capacity restrictions:** upload time in the `primary_key` only; staging keeps the latest upload.
- **ENTSO-E energy prices:** document id in the `primary_key` only; staging keeps the latest update.
- **REMIT (`ods_unavailability`):** no mart; builds rebuild whole events ([ADR 0004](adr/0004-remit-events-and-resource-schemes.md)).
- **EIC codes:** unallocated codes publishers use are kept, after review, as the code they stand for ([ADR 0005](adr/0005-nonconforming-eic-codes.md)).
- **Landing zone:** not yet loaded into `raw` ([services](../services/README.md)).

## Appendix B: Details

| Where | Departure | Why |
|---|---|---|
| Elexon streams | `merge` + `delete-insert` | the API repeats records verbatim within a load, and dlt's `scd2` keeps each copy |
| ECMWF forecast runs | only the named fields at the grid points nearest the selected sites (`dim_site`) | a global grid is billions of values a day |
| NESO capacity restrictions | the upload time joins the `primary_key` but not the `merge_key` | NESO at times appends a resubmission instead of replacing it |
| ENTSO-E energy prices | the document id (`InstanceCode`) joins the `primary_key` but not the `merge_key` | an export lists several documents per natural key |
| REMIT | no mart; a build rebuilds every message of a touched event | messages are combined with the data they concern in analytical queries |
| EIC codes | kept as the registered code they stand for | publishers' data uses them |
| Landing zone | not loaded into `raw` | the services are work in progress |
