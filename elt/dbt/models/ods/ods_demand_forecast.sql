with unioned as (
    select
        timestamp_utc, cast(null as integer) as interval_minutes, cast(null as varchar) as area_eic_code, demand_mw,
        'NDF' as source_dataset, settlement_date, settlement_period, publish_time_utc, _dlt_load_id
    from {{ pending_partitions(ref('stg_bmrs__ndf')) }}

    union all

    select
        timestamp_utc, interval_minutes, area_eic_code, demand_mw,
        'ENTSOE_6.1.B' as source_dataset, cast(null as date) as settlement_date, cast(null as integer) as settlement_period,
        publish_time_utc, _dlt_load_id
    from {{ pending_partitions(ref('stg_entsoe__day_ahead_total_load_forecast'), ['area_eic_code']) }}
)

-- the interval and area each source publishes, else the dataset's (dim_source_dataset); each dataset is
-- one horizon (map_time_horizon)
select
    u.timestamp_utc,
    coalesce(u.interval_minutes, ds.native_interval_minutes) as interval_minutes,
    coalesce(u.area_eic_code, ds.default_area_eic_code) as area_eic_code,
    h.time_horizon,
    u.demand_mw,
    u.source_dataset,
    u.settlement_date,
    u.settlement_period,
    u.publish_time_utc,
    u._dlt_load_id
from unioned u
left join {{ ref('dim_source_dataset') }} ds on ds.source_dataset = u.source_dataset
left join {{ ref('map_time_horizon') }} h on h.source_dataset = u.source_dataset and h.source_code = '*'
