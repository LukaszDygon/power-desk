select
    s.timestamp_utc,
    ds.native_interval_minutes as interval_minutes,
    ds.default_area_eic_code as area_eic_code,
    'day_ahead' as forecast_horizon,
    s.demand_mw,
    ds.source_dataset,
    s.settlement_date,
    s.settlement_period,
    s.publish_time_utc,
    s._dlt_load_id
from {{ ref('stg_bmrs__ndf') }} s
join {{ ref('source_datasets') }} ds on ds.source_dataset = 'NDF'

union all

select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    'day_ahead' as forecast_horizon,
    demand_mw,
    'ENTSOE_6.1.B' as source_dataset,
    cast(null as date) as settlement_date,
    cast(null as integer) as settlement_period,
    publish_time_utc,
    _dlt_load_id
from {{ ref('stg_entsoe__day_ahead_total_load_forecast') }}
