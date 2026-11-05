with unioned as (
    -- MID publishes no publication time
    select
        timestamp_utc, cast(null as integer) as interval_minutes, cast(null as varchar) as area_eic_code,
        cast(null as varchar) as horizon_code, cast(null as integer) as classification_sequence, price_per_mwh,
        'GBP' as currency, volume_mwh, 'MID' as source_dataset, data_provider as source_code, settlement_date,
        settlement_period, cast(null as timestamp) as publish_time_utc, _dlt_load_id
    from {{ pending_partitions(ref('stg_bmrs__mid')) }}

    union all

    select
        timestamp_utc, interval_minutes, area_eic_code, contract_type as horizon_code, classification_sequence,
        price_per_mwh, currency, cast(null as double) as volume_mwh, 'ENTSOE_12.1.D' as source_dataset,
        contract_type as source_code, cast(null as date) as settlement_date, cast(null as integer) as settlement_period,
        publish_time_utc, _dlt_load_id
    from {{ pending_partitions(ref('stg_entsoe__energy_prices'), ['area_eic_code']) }}
)

-- the interval and area each source publishes, else the dataset's (dim_source_dataset); ENTSO-E contract
-- types map onto time horizons (map_time_horizon), MID has none
select
    u.timestamp_utc,
    coalesce(u.interval_minutes, ds.native_interval_minutes) as interval_minutes,
    coalesce(u.area_eic_code, ds.default_area_eic_code) as area_eic_code,
    h.time_horizon,
    u.classification_sequence,
    u.price_per_mwh,
    u.currency,
    u.volume_mwh,
    u.source_dataset,
    u.source_code,
    u.settlement_date,
    u.settlement_period,
    u.publish_time_utc,
    u._dlt_load_id
from unioned u
left join {{ ref('dim_source_dataset') }} ds on ds.source_dataset = u.source_dataset
left join {{ ref('map_time_horizon') }} h on h.source_dataset = 'ENTSOE_CONTRACT_TYPE' and h.source_code = u.horizon_code
