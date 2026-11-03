{#- keyed by row: delete+insert joins on the key, so a coarser one (the run) multiplies rows quadratically -#}
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['publish_time_utc', 'step_hours', 'param_id', 'grid_latitude', 'grid_longitude'],
    meta={'dlt_tracked': true}
) }}

{{ stg_ecmwf_fields('ecmwf__ifs_oper') }}
