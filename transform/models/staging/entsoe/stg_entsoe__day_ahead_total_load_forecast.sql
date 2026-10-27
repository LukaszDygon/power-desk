{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='_source_file', meta={'dlt_tracked': true}) }}

select
    cast(date_time_utc at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('resolution_code') }} as interval_minutes,
    area_code as area_eic_code,
    area_type_code,
    area_map_code,
    total_load_mw as demand_mw,
    cast(update_time_utc at time zone 'UTC' as timestamp) as publish_time_utc,
    _source_file,
    _dlt_load_id
from {{ dlt_source('entsoe', 'entsoe__day_ahead_total_load_forecast') }}
where {{ dlt_incremental_filter('_dlt_load_id') }}
{{ keep_finest_resolution(['area_eic_code']) }}
