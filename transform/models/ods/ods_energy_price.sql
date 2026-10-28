select
    s.timestamp_utc,
    ds.native_interval_minutes as interval_minutes,
    ds.default_area_eic_code as area_eic_code,
    cast(null as varchar) as time_horizon,
    cast(null as integer) as classification_sequence,
    s.price_per_mwh,
    'GBP' as currency,
    s.volume_mwh,
    ds.source_dataset,
    s.data_provider as source_code,
    s.settlement_date,
    s.settlement_period,
    s.timestamp_utc + to_minutes(ds.native_interval_minutes) as publish_time_utc,
    s._dlt_load_id
from {{ ref('stg_bmrs__mid') }} s
join {{ ref('source_datasets') }} ds on ds.source_dataset = 'MID'

union all

select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    case contract_type when 'Day-ahead' then 'day_ahead' when 'Intraday' then 'intraday' end as time_horizon,
    classification_sequence,
    price_per_mwh,
    currency,
    cast(null as double) as volume_mwh,
    'ENTSOE_12.1.D' as source_dataset,
    contract_type as source_code,
    cast(null as date) as settlement_date,
    cast(null as integer) as settlement_period,
    publish_time_utc,
    _dlt_load_id
from {{ ref('stg_entsoe__energy_prices') }}
-- an area changing its market time unit publishes the overlap at both resolutions: keep the finest
{{ keep_finest_resolution(['area_eic_code', 'source_code', 'classification_sequence']) }}
