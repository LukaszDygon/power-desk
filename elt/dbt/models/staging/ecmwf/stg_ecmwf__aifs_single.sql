{#- keyed by row: delete+insert joins on the key, so a coarser one (the run) multiplies rows quadratically.
    The key follows raw's natural key (short name, not parameter id), so a new version of a raw row replaces
    the staged one even if its parameter id changed. -#}
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['publish_time_utc', 'step_hours', 'short_name', 'grid_latitude', 'grid_longitude'],
    meta={'dlt_tracked': true}
) }}

{{ stg_ecmwf_fields('ecmwf__aifs_single') }}
