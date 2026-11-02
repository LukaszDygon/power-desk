with periods as (
    select
        datetime_gmt - interval 30 minute as period_start,
        datetime_gmt,
        generation_mw,
        _dlt_load_id
    from {{ dlt_source('pvlive', 'pvlive__solar') }}
    where pes_id = 0
)

select
    cast(period_start at time zone 'UTC' as timestamp) as timestamp_utc,
    {{ utc_to_settlement_date('period_start') }} as settlement_date,
    {{ utc_to_settlement_period('period_start') }} as settlement_period,
    cast(generation_mw as double) as generation_mw,
    cast(datetime_gmt at time zone 'UTC' as timestamp) as publish_time_utc,
    _dlt_load_id
from periods
