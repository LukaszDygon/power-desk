# Platform (local cluster)

What runs beside our code on the local minikube cluster: log aggregation and the catalogue. Each is a set of
pinned Helm charts with values for a small local cluster (`make` targets in `Makefile`); a real cluster
needs its own values (authentication, storage, sizes).

| Namespace | Charts | For |
|---|---|---|
| `power-desk` | our services (`services/`) | push feeds |
| `observability` | Loki (single binary), Alloy, Grafana | logs: every pod's, and the local Dagster runs' |
| `openmetadata` | MySQL, OpenSearch, OpenMetadata | the catalogue |

```bash
make -C platform cluster          # minikube; repository's data/ mounted at /power-desk-data
make -C platform observability    # then: make -C platform grafana        -> http://localhost:3000
make -C platform openmetadata     # then: make -C platform openmetadata-ui -> http://localhost:8585
make -C platform catalog          # with openmetadata-ui running: register the warehouse and dbt project
make -C platform openmetadata-down  # stop the catalogue; its volumes (MySQL, OpenSearch) stay
make -C platform down             # delete the cluster; data/ stays
```

## Logs (Grafana)

- **Collection:** Alloy (`observability/config.alloy`) tails every pod through the Kubernetes API and the
  local Dagster run log (`data/logs/<env>/dagster-runs.jsonl`, via the mount), and parses records in the
  [log standard](../docs/logging.md): `level`, `service_name`, `environment` and `event_name` become labels;
  `dagster_run_id`, `dagster_step_key`, `dlt_pipeline_name`, `dlt_load_id`, `scope` and `exception_type`
  structured metadata. Other lines pass as they are (Loki detects their level).
- **Storage:** Loki on its volume, a week (`observability/loki.yaml`).
- **Viewing:** Grafana (anonymous admin, local only) with Loki provisioned and the dashboard *Power Desk
  logs*: records by level, dlt loads, errors and the log stream, filtered by service, level, Dagster run id,
  dlt load id or text. Explore and Logs Drilldown work on the same labels, e.g.
  `{event_name="dlt.load"} | dlt_load_id="<id>"`.

## Catalogue (OpenMetadata)

- **Memory:** minimum sizes for trying things out: no Airflow, small heaps (OpenSearch 512 MB, server
  640 MB), about 2.3 GB. On an 8 GB machine run one stack at a time (`observability-down`, then
  `openmetadata`) on a node of about 3.5 GB (`make cluster MEMORY=3500`; minikube's default is a quarter of
  the machine). Both together need about 6 GB.
- **Login:** `admin@open-metadata.org` / `admin` (the chart's default; local only).
- **Ingestion from the CLI:** `make catalog` compiles dbt's manifest and catalog into
  `transform/target/openmetadata` (the newest build's `run_results.json` gives the tests), reads the ingestion bot's
  token (`openmetadata/bot_token.py`), then runs the two workflows of
  [openmetadata-duckdb](../integrations/openmetadata-duckdb/README.md) from its environment: the warehouse's
  schemas, tables and columns, then dbt's descriptions, lineage and tests. Run it between Dagster runs
  (DuckDB allows one writer).
- **Images:** Docker Hub pulls go through `mirror.gcr.io` (the cluster's registry mirror).
