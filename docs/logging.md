# Logging and provenance

How every process logs, and how a row is traced back through logs, dlt metadata and dbt artifacts to its load.

## Standard

- **One record format:** the [OpenTelemetry log data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/), implemented once in `libs/logging` (Appendix B).
- **Tool identifiers, not ours:** records carry the ids dlt, dbt and Dagster issue; OpenMetadata ingests the same ids.
- **Settings:** `POWER_DESK_LOG_LEVEL` (`INFO`), `RUNTIME__LOG_LEVEL` for dlt (`WARNING`), `POWER_DESK_LOG_FORMAT` (`text` or `json`).

## Hygiene

- **Log in shared code:** context is bound where a unit of work starts; modules log plain messages.
- **Configure libraries, don't re-log them:** route and enrich dlt, dbt and Dagster records.
- **One setup call per process:** `configure(service)`, or `instrument()` under Dagster.
- **Never:** secrets, row data, or `print` outside CLI output for people.
- **Levels:** `INFO` is what happened to data; `ERROR` is data lost or delayed (Appendix B).

## Provenance

- **Identifiers:** `dagster.run_id`, `dlt.pipeline_name`, `dlt.load_id`, `dbt.invocation_id` (Appendix B).
- **One event:** `dlt.load` per load package of every dlt run; dbt needs none.
- **Tracing a row:** its load id leads to `raw._dlt_loads`, the `dlt.load` event and `dlt_load_audit`'s dbt invocation and Dagster run (Appendix B).
- **Where records go:** stderr (services, CLIs), Dagster's event log plus a JSON run log, `dbt.log` beside its artifacts; Loki and Grafana on the cluster ([infra](../infra/README.md)).

## OpenMetadata

- **Sources:** the warehouse ([our DuckDB connector](../infra/openmetadata-duckdb/README.md)), dbt artifacts, Dagster, OpenLineage events (Appendix B).
- **Open:** emitting OpenLineage events, keeping dbt artifacts until ingested, the landing load id in raw.

## Appendix B: Details

**Hygiene.** Units of work: a pipeline run, a queue, a Dagster run; modules use `logging.getLogger(__name__)`.
`extra={...}` only for a fact about one record (a dead-lettered message id). Routing: dlt through its tracking
hook, dbt through its JSON log file and run id, Dagster through `python_logs`; an event is added only where a
tool has none (`dlt.load`). `configure` serves services and CLIs; `instrument()` is for frameworks owning the
handlers. Levels: `DEBUG` diagnostics; `INFO` what happened to data; `WARNING` handled anomalies (rejected
input, retries); `ERROR` a failure that loses or delays data; `CRITICAL` the process stopped.
`POWER_DESK_LOG_FORMAT=text` is a line for people, `json` is for collectors (the services' image).

**Record**, as dbt writes its own JSON logs:

| Field | |
|---|---|
| `timestamp` | UTC, ISO 8601 |
| `severity_text`, `severity_number` | Python level and its OpenTelemetry number (INFO 9, WARNING 13, ERROR 17) |
| `body` | the message, readable on its own |
| `event_name` | provenance events only |
| `scope_name` | the logger: the module, or `dlt` |
| `resource` | `service.namespace` (`power-desk`), `service.name`, `deployment.environment.name` (`POWER_DESK_ENV`), `host.name` (the pod), `process.pid` |
| `attributes` | below, by [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/) where one exists, otherwise the tool's own field under its name |

| Attributes | Added by |
|---|---|
| `dlt.pipeline_name`, `dlt.step`, `dlt.load_id` | every record during a dlt run (`dlt_tracking`, dlt's `TRACKING_MODULES` hook); the load id once extracted |
| `dagster.run_id`, `dagster.job_name`, `dagster.step_key`, `dagster.event_type` | every record of a Dagster run (Dagster's record metadata) |
| `messaging.system`, `messaging.destination.name` | every IRIS record (`log_context` around the consumer) |
| `code.function.name`, `code.file.path`, `code.line.number`, `thread.name` | every record (JSON only) |
| `exception.type`, `exception.message`, `exception.stacktrace` | records with an exception, and an uncaught one (`configure`) |

**Identifiers.**

| Attribute | Issued by | Also in |
|---|---|---|
| `dagster.run_id` | Dagster, per run | the run's event log; dbt `metadata.env.DAGSTER_RUN_ID` (artifacts and `dbt.log`) |
| `dlt.pipeline_name` | dlt pipeline (= source) | `raw._dlt_loads.schema_name`, `raw._dlt_pipeline_state` |
| `dlt.load_id` | dlt, per load package | `raw._dlt_loads.load_id`, `_dlt_load_id` of every raw row, `dlt_load_audit.load_id`, `_last_dlt_load_id` of mart rows; landing files `<table>/<load_id>.*` |
| `dbt.invocation_id` | dbt, per invocation | `metadata.invocation_id` of `manifest.json` / `run_results.json`, every `dbt.log` line, `dlt_load_audit.dbt_invocation_id` |

dbt receives the Dagster run id as `DBT_ENV_CUSTOM_ENV_DAGSTER_RUN_ID`, which it
[stamps into its artifacts](https://docs.getdbt.com/reference/dbt-jinja-functions/env_var#custom-metadata)
and log lines; `DBT_LOG_FORMAT_FILE=json` makes `dbt.log` JSON lines.

**`dlt.load` event.** Emitted by the tracking hook for every dlt run (orchestrator, CLIs, services), with
`dlt.pipeline_name`, `dlt.destination_name`, `dlt.dataset_name`, `dlt.load_id`, `dlt.row_counts` (table → rows,
from dlt's normalize metrics). dbt's log and artifacts carry both ids, and `dlt_load_audit` links its
invocations to the loads.

**Where records go.**

| Process | Destination |
|---|---|
| Services (`services/`) | stderr, JSON in the image; the cluster collects it |
| Dagster runs | the run's event log (UI), and JSON lines in `data/logs/<env>/dagster-runs.jsonl` (`orchestration/logs.py`, via `python_logs` in `dagster.yaml`); the console keeps Dagster's format |
| dbt | `dbt.log` next to the invocation's artifacts: `elt/dbt/target/dbt_models-<run>-<hash>/` in Dagster, `elt/dbt/target/` from the CLIs |
| CLIs (`power-desk-load-seed`, `power-desk-accept`) | stderr |

On the local cluster, Alloy ships the pods' records and the Dagster run log to Loki, viewed in Grafana and
filtered by the identifiers above.

**Tracing a row.**

1. A mart row names its `source_dataset` and `_last_dlt_load_id`; an ods or raw row its `_dlt_load_id`.
2. `raw._dlt_loads` dates the load (ingestion time comes only from dlt's metadata); its `dlt.load` event
   gives the pipeline, row counts and Dagster run, and the run's records what happened while it loaded.
3. `dlt_meta.dlt_load_audit` names the dbt invocation and Dagster run that built each tracked mart from it;
   that invocation's `manifest.json`, `run_results.json` and `dbt.log` show the SQL, tests and timings.
4. Pushed feeds: landed files are named by the landing load id, whose `dlt.load` event names the service.

**OpenMetadata.**

| Metadata | OpenMetadata reads it from |
|---|---|
| Schemas, tables, views, columns | the warehouse: our [DuckDB connector](../infra/openmetadata-duckdb/README.md) (OpenMetadata has none) |
| Descriptions, model lineage, test results | dbt artifacts: [dbt connector](https://docs.open-metadata.org/v2.0.x/connectors/database/dbt) |
| Jobs, runs and their status | Dagster: [Dagster connector](https://docs.open-metadata.org/v2.0.x/connectors/pipeline/dagster) |
| Publisher → raw and landing lineage | OpenLineage run events to its [OpenLineage API](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-lineage/openlineage) |

Planned OpenLineage events: one per `dlt.load` event, job `<namespace>.<pipeline>`, run id a UUID of the load
id, parent run the Dagster run, outputs the loaded tables; the event carries every field. The landing load id
should survive into raw once the landing zone is onboarded.
