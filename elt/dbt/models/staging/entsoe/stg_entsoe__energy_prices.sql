{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['timestamp_utc', 'area_eic_code', 'area_type_code', 'contract_type'],
    meta={'dlt_tracked': true}
) }}

-- Current versions (scd2) under each (time, area, contract type) pending loads wrote, every sequence
-- and resolution (a null sequence cannot be a delete+insert key); of several current documents per
-- natural key, the latest update, as the platform publishes it.
with current_rows as (
    select * from {{ dlt_source('entsoe', 'entsoe__energy_prices') }}
    where _dlt_valid_to is null
),

touched as (
    select distinct date_time_utcx, area_code, area_type_code, contract_type
    from current_rows
    where {{ dlt_incremental_filter('_dlt_load_id') }}
)

select
    cast(c.date_time_utcx at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ iso8601_duration_minutes('c.resolution_code') }} as interval_minutes,
    c.area_code as area_eic_code,
    c.area_type_code,
    c.area_map_code,
    c.contract_type,
    cast(nullif(trim(c.sequence), '') as integer) as classification_sequence,
    c.price_currency_m_whx as price_per_mwh,
    c.currency,
    c.instance_code,
    cast(c.update_time_utcx at time zone 'UTC' as timestamp) as publish_time_utc,
    c._dlt_load_id
from current_rows c
semi join touched t using (date_time_utcx, area_code, area_type_code, contract_type)
qualify row_number() over (
    partition by c.date_time_utcx, c.resolution_code, c.area_code, c.area_type_code, c.contract_type, c.sequence
    order by c.update_time_utcx desc, c.instance_code desc
) = 1
