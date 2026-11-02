select
    cast(start_time at time zone 'UTC' as timestamp) as timestamp_utc,
    cast(settlement_date as date) as settlement_date,
    cast(settlement_period as integer) as settlement_period,
    data_provider,
    cast(price as double) as price_per_mwh,
    cast(volume as double) as volume_mwh,
    _dlt_load_id
from {{ dlt_source('bmrs', 'bmrs__mid') }}
where settlement_date is not null
