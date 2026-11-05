{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['timestamp_utc', 'interval_minutes', 'area_eic_code', 'area_type_code', 'production_type'],
    meta={'dlt_tracked': true}
) }}

-- the current version (scd2) of each row pending loads wrote, replacing the earlier version per natural key
select
    cast(f.date_time_utcx at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('f.resolution_code') }} as interval_minutes,
    f.area_code as area_eic_code,
    f.area_type_code,
    f.area_map_code,
    f.production_type,
    {{ entsoe_psr_type('f.production_type') }} as psr_type,
    f.day_ahead_generation_forecast_mwx as day_ahead_forecast_mw,
    f.intraday_generation_forecast_mwx as intraday_forecast_mw,
    f.current_generation_forecast_mwx as current_forecast_mw,
    cast(f.update_time_utcx at time zone 'UTC' as timestamp) as publish_time_utc,
    f._dlt_load_id
from {{ dlt_source('entsoe', 'entsoe__wind_solar_forecast') }} f
where f._dlt_valid_to is null and {{ dlt_incremental_filter('f._dlt_load_id') }}
