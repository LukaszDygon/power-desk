select
    cast(start_time at time zone 'UTC' as timestamp) as timestamp_utc,
    cast(settlement_date as date) as settlement_date,
    cast(settlement_period as integer) as settlement_period,
    upper(trim(fuel_type)) as fuel_type,
    cast(generation as double) as generation_mw,
    cast(publish_time at time zone 'UTC' as timestamp) as publish_time_utc,
    _dlt_load_id
from {{ source('bmrs', 'raw_fuelinst') }}
where fuel_type is not null
  -- PVLIVE rows in this table are not FUELINST records; solar comes from the pvlive source
  and coalesce(dataset, 'FUELINST') <> 'PVLIVE'
