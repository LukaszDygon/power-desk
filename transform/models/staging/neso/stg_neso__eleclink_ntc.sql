{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['timestamp_utc', 'auction_type'],
    meta={'dlt_tracked': true}
) }}

{{ stg_neso_ntc('neso__eleclink_ntc') }}
