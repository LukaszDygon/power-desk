{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='_source_file', meta={'dlt_tracked': true}) }}

select
    cast(f.date_time_utc at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('f.resolution_code') }} as interval_minutes,
    f.area_code as area_eic_code,
    f.area_type_code,
    f.area_map_code,
    f.production_type,
    p.psr_type,
    f.day_ahead_generation_forecast_mw as day_ahead_forecast_mw,
    f.intraday_generation_forecast_mw as intraday_forecast_mw,
    f.current_generation_forecast_mw as current_forecast_mw,
    cast(f.update_time_utc at time zone 'UTC' as timestamp) as publish_time_utc,
    f._source_file,
    f._dlt_load_id
from {{ dlt_source('entsoe', 'entsoe__wind_solar_forecast') }} f
left join {{ ref('entsoe_psr_types') }} p on p.production_type = f.production_type
where {{ dlt_incremental_filter('f._dlt_load_id') }}
{{ keep_finest_resolution(['f.area_code', 'f.production_type']) }}
