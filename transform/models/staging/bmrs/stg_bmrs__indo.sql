select
    {{ settlement_period_to_utc('settlement_date', 'settlement_period') }} as timestamp_utc,
    cast(settlement_date as date) as settlement_date,
    cast(settlement_period as integer) as settlement_period,
    cast(demand as double) as demand_mw,
    cast(publish_time at time zone 'UTC' as timestamp) as publish_time_utc,
    _dlt_load_id
from {{ source('bmrs', 'raw_indo') }}
where settlement_date is not null
