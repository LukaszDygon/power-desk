{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['timestamp_utc', 'interval_minutes', 'area_eic_code', 'area_type_code', 'production_type'],
    meta={'dlt_tracked': true}
) }}

-- the current version (scd2) of each row pending loads wrote, replacing the earlier version per natural key
select
    cast(g.date_time_utcx at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('g.resolution_code') }} as interval_minutes,
    g.area_code as area_eic_code,
    g.area_type_code,
    g.area_map_code,
    g.production_type,
    p.psr_type,
    g.actual_generation_output_mwx as generation_mw,
    g.actual_consumption_mwx as consumption_mw,
    cast(g.update_time_utcx at time zone 'UTC' as timestamp) as publish_time_utc,
    g._dlt_load_id
from {{ dlt_source('entsoe', 'entsoe__generation_per_type') }} g
left join {{ ref('entsoe_psr_types') }} p on p.production_type = g.production_type
where g._dlt_valid_to is null and {{ dlt_incremental_filter('g._dlt_load_id') }}
