{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['timestamp_utc', 'interval_minutes', 'area_eic_code', 'area_type_code'],
    meta={'dlt_tracked': true}
) }}

-- the current version (scd2) of each row pending loads wrote, replacing the earlier version per natural key
select
    cast(date_time_utcx at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('resolution_code') }} as interval_minutes,
    area_code as area_eic_code,
    area_type_code,
    area_map_code,
    total_load_mwx as demand_mw,
    cast(update_time_utcx at time zone 'UTC' as timestamp) as publish_time_utc,
    _dlt_load_id
from {{ dlt_source('entsoe', 'entsoe__actual_total_load') }}
where _dlt_valid_to is null and {{ dlt_incremental_filter('_dlt_load_id') }}
