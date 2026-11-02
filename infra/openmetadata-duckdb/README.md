# openmetadata-duckdb

An [OpenMetadata custom database connector](https://docs.open-metadata.org/v2.0.x/connectors/custom-connectors)
for a DuckDB file. OpenMetadata has no DuckDB connector; this registers the file's schemas, tables, views
(with their SQL) and columns (OpenMetadata types, DuckDB's as displayed), so the dbt connector and lineage
events can attach to them. Built on OpenMetadata's
[custom connector example](https://github.com/open-metadata/openmetadata-demo/tree/main/custom-connector).

Its own project and lock (outside the uv workspace): it runs inside OpenMetadata's ingestion image, with its
pins. Keep `openmetadata-ingestion` at the server's version and `duckdb` at the warehouse's.

```bash
make check-connector                                                    # from the repository root
docker build -f docker/Dockerfile -t openmetadata-ingestion-duckdb .   # from this directory
```

Workflows (`metadata ingest -c <config>`, or as a Custom database service in the UI with
`openmetadata_duckdb.source.DuckDBSource`):

1. `configs/warehouse.yaml`: the warehouse (`POWER_DESK_DUCKDB_PATH`), opened read-only, so between writes.
2. `configs/dbt.yaml`: descriptions, model lineage and test results: the manifest and catalog of
   `dbt compile --write-catalog` into its own target (`DBT_CATALOG_PATH`; dbt Fusion's `docs generate` writes
   no catalog), and a build's `run_results.json` (`DBT_RUN_RESULTS`). dbt names the database after the
   warehouse file it built (`warehouse_dev`); use the same file in step 1.
