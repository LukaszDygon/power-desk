# Deviations

Every place the code departs from the [architecture](architecture.md), with its reason. Keep this list
short: remove an entry when the departure goes, and add one only with the user's agreement.

| Where | Departure | Why | Record |
|---|---|---|---|
| Elexon streams (`bmrs`, except REMIT) | `merge` + `delete-insert`, not `scd2`: no time travel | the API repeats records verbatim within a load, and dlt's `scd2` keeps each copy | [ADR 0001](adr/0001-keep-dlt-defaults-for-ingestion.md) |
| ECMWF forecast runs | raw keeps only the named fields at the grid points nearest the selected sites (`dim_site`), not the published grid | a global grid is billions of values a day | [ADR 0006](adr/0006-gridded-forecasts-at-named-points.md) |
| NESO capacity restrictions | the upload time joins the `primary_key` but not the `merge_key`; staging keeps the latest upload | NESO at times appends a resubmission instead of replacing it | |
| ENTSO-E energy prices | the document id (`InstanceCode`) joins the `primary_key` but not the `merge_key`; staging keeps the latest update | an export lists several documents per natural key | |
| REMIT (`ods_unavailability`) | no mart; a build rebuilds every message of a touched event | messages are combined with the data they concern in analytical queries | [ADR 0004](adr/0004-remit-events-and-resource-schemes.md) |
| EIC codes | codes publishers use as EICs that no office allocated are kept, after review, as the registered code they stand for | publishers' data uses them | [ADR 0005](adr/0005-nonconforming-eic-codes.md) |
| Landing zone | not yet loaded into `raw` | the services are work in progress | [services](../services/README.md) |
