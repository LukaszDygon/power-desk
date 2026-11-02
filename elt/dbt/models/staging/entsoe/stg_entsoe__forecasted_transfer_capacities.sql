{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['timestamp_utc', 'out_area_eic_code', 'out_area_type_code', 'in_area_eic_code', 'in_area_type_code', 'contract_type'],
    meta={'dlt_tracked': true}
) }}

-- Current versions (scd2) under each (time, oriented couple of areas, contract type) pending loads
-- wrote, every resolution.
with current_rows as (
    select * from {{ dlt_source('entsoe', 'entsoe__forecasted_transfer_capacities') }}
    where _dlt_valid_to is null
),

touched as (
    select distinct date_time_utcx, out_area_code, out_area_type_code, in_area_code, in_area_type_code, contract_type
    from current_rows
    where {{ dlt_incremental_filter('_dlt_load_id') }}
)

select
    cast(c.date_time_utcx at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('c.resolution_code', "cast(c.date_time_utcx at time zone 'UTC' as timestamp)") }} as interval_minutes,
    c.out_area_code as out_area_eic_code,
    c.out_area_type_code,
    c.out_area_map_code,
    c.in_area_code as in_area_eic_code,
    c.in_area_type_code,
    c.in_area_map_code,
    c.contract_type,
    c.forecast_transfer_capacity_mwx as transfer_capacity_mw,
    cast(c.update_time_utcx at time zone 'UTC' as timestamp) as publish_time_utc,
    c._dlt_load_id
from current_rows c
semi join touched t using (date_time_utcx, out_area_code, out_area_type_code, in_area_code, in_area_type_code, contract_type)
