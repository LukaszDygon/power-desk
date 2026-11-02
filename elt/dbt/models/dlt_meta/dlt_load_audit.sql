-- rows are written by the `dlt_mark_loads_processed` on-run-end hook
{{ config(materialized='incremental', incremental_strategy='append', full_refresh=false) }}

select
    cast(null as varchar) as load_id,
    cast(null as varchar) as model_name,
    cast(null as varchar) as dbt_invocation_id,
    cast(null as varchar) as orchestrator_run_id,
    cast(null as timestamp with time zone) as processed_at
where false
