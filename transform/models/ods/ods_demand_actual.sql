select
    s.timestamp_utc,
    ds.native_interval_minutes as interval_minutes,
    ds.default_area_eic_code as area_eic_code,
    s.demand_mw,
    ds.source_dataset,
    s.settlement_date,
    s.settlement_period,
    s.publish_time_utc,
    s._dlt_load_id
from {{ ref('stg_bmrs__indo') }} s
join {{ ref('source_datasets') }} ds on ds.source_dataset = 'INDO'

union all

select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    demand_mw,
    'ENTSOE_6.1.A' as source_dataset,
    cast(null as date) as settlement_date,
    cast(null as integer) as settlement_period,
    publish_time_utc,
    _dlt_load_id
from {{ ref('stg_entsoe__actual_total_load') }}
-- an area changing its market time unit publishes the overlap at both resolutions: keep the finest
{{ keep_finest_resolution(['area_eic_code']) }}
