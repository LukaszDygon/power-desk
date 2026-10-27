{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='_source_file', meta={'dlt_tracked': true}) }}

select
    cast(g.date_time_utc at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('g.resolution_code') }} as interval_minutes,
    g.area_code as area_eic_code,
    g.area_type_code,
    g.area_map_code,
    g.production_type,
    p.psr_type,
    g.actual_generation_output_mw as generation_mw,
    g.actual_consumption_mw as consumption_mw,
    cast(g.update_time_utc at time zone 'UTC' as timestamp) as publish_time_utc,
    g._source_file,
    g._dlt_load_id
from {{ dlt_source('entsoe', 'entsoe__generation_per_type') }} g
left join {{ ref('entsoe_psr_types') }} p on p.production_type = g.production_type
where {{ dlt_incremental_filter('g._dlt_load_id') }}
{{ keep_finest_resolution(['g.area_code', 'g.production_type']) }}
