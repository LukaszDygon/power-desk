# Logging and provenance

Every process logs one record format, and records about data carry the identifiers dlt, dbt and Dagster
already issue, so a row's provenance is traceable through logs, dlt metadata and dbt artifacts, and the same
identifiers are what a catalogue (OpenMetadata) ingests. The standard is implemented once, in
`libs/logging` (`power_desk_logging`).

## Hygiene

- **Log in shared code, not at call sites.** Context is bound where a unit of work starts (a pipeline run, a
  queue, a Dagster run) and enriches every record within it; modules log plain messages with
  `logging.getLogger(__name__)`. `extra={...}` only for a fact about one record (a dead-lettered message id).
- **Configure libraries rather than re-log them.** dlt logs and traces its runs, dbt its invocations,
  Dagster its steps: we route and enrich their records (dlt: its tracking hook; dbt: JSON log file and run id;
  Dagster: `python_logs`), and add an event only where a tool has none (`dlt.load`).
- **One setup call per process:** `configure(service)` (services, CLIs), or `instrument()` where a framework
  owns the handlers (Dagster).
- **No secrets, no row data, no `print`** outside CLI output meant for people.
- **Levels:** `DEBUG` diagnostics; `INFO` what happened to data; `WARNING` handled anomalies (rejected input,
  retries); `ERROR` a failure that loses or delays data; `CRITICAL` the process stopped.

## Record

The [OpenTelemetry log data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/), as dbt
writes its own JSON logs.

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

`POWER_DESK_LOG_LEVEL` (`INFO`) sets our level, `RUNTIME__LOG_LEVEL` dlt's (its default, `WARNING`).
`POWER_DESK_LOG_FORMAT` is `text` (a line for people) or `json` (collectors; the services' image).

## Identifiers

| Attribute | Issued by | Also in |
|---|---|---|
| `dagster.run_id` | Dagster, per run | the run's event log; dbt `metadata.env.DAGSTER_RUN_ID` (artifacts and `dbt.log`) |
| `dlt.pipeline_name` | dlt pipeline (= source) | `raw._dlt_loads.schema_name`, `raw._dlt_pipeline_state` |
| `dlt.load_id` | dlt, per load package | `raw._dlt_loads.load_id`, `_dlt_load_id` of every raw row, `dlt_load_audit.load_id`, `_last_dlt_load_id` of mart rows; landing files `<table>/<load_id>.*` |
| `dbt.invocation_id` | dbt, per invocation | `metadata.invocation_id` of `manifest.json` / `run_results.json`, every `dbt.log` line, `dlt_load_audit.dbt_invocation_id` |

dbt receives the Dagster run id as `DBT_ENV_CUSTOM_ENV_DAGSTER_RUN_ID`, which it
[stamps into its artifacts](https://docs.getdbt.com/reference/dbt-jinja-functions/env_var#custom-metadata)
and log lines; `DBT_LOG_FORMAT_FILE=json` makes `dbt.log` JSON lines.

## Provenance event

`dlt.load`, one per load package of every dlt run (orchestrator, CLIs, services), from the tracking hook:
`dlt.pipeline_name`, `dlt.destination_name`, `dlt.dataset_name`, `dlt.load_id`, `dlt.row_counts` (table →
rows, from dlt's normalize metrics). dbt needs none: its log and artifacts carry both ids, and
`dlt_load_audit` links its invocations to the loads.

## Where records go

| Process | Destination |
|---|---|
| Services (`services/`) | stderr, JSON in the image; the cluster collects it |
| Dagster runs | the run's event log (UI), and JSON lines in `data/logs/<env>/dagster-runs.jsonl` (`orchestration/logs.py`, via `python_logs` in `dagster.yaml`); the console keeps Dagster's format |
| dbt | `dbt.log` next to the invocation's artifacts: `elt/dbt/target/dbt_models-<run>-<hash>/` in Dagster, `elt/dbt/target/` from the CLIs |
| CLIs (`power-desk-load-seed`, `power-desk-accept`) | stderr |

On the local cluster, Alloy ships the pods' records and the Dagster run log to Loki, viewed in Grafana and
filtered by the identifiers above ([infra](../infra/README.md)).

## Tracing a row

1. A mart row names its `source_dataset` and `_last_dlt_load_id`; an ods or raw row its `_dlt_load_id`.
2. `raw._dlt_loads` dates the load (ingestion time comes only from dlt's metadata); its `dlt.load` event
   gives the pipeline, row counts and Dagster run, and the run's records what happened while it loaded.
3. `dlt_meta.dlt_load_audit` names the dbt invocation and Dagster run that built each tracked mart from it;
   that invocation's `manifest.json`, `run_results.json` and `dbt.log` show the SQL, tests and timings.
4. Pushed feeds: landed files are named by the landing load id, whose `dlt.load` event names the service.

## OpenMetadata

| Metadata | OpenMetadata reads it from |
|---|---|
| Schemas, tables, views, columns | the warehouse: our [DuckDB connector](../infra/openmetadata-duckdb/README.md) (OpenMetadata has none) |
| Descriptions, model lineage, test results | dbt artifacts: [dbt connector](https://docs.open-metadata.org/v2.0.x/connectors/database/dbt) |
| Jobs, runs and their status | Dagster: [Dagster connector](https://docs.open-metadata.org/v2.0.x/connectors/pipeline/dagster) |
| Publisher → raw and landing lineage | OpenLineage run events to its [OpenLineage API](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-lineage/openlineage) |

Open: emitting OpenLineage events (one per `dlt.load` event: job `<namespace>.<pipeline>`, run id a UUID of
the load id, parent run the Dagster run, outputs the loaded tables; the event carries every field); keeping
each invocation's dbt artifacts until ingested; the landing load id surviving into raw once the landing zone
is onboarded.
