with ranked as (
    select
        {{ settlement_period_to_utc('settlement_date', 'settlement_period') }} as timestamp_utc,
        cast(settlement_date as date) as settlement_date,
        cast(settlement_period as integer) as settlement_period,
        cast(demand as double) as demand_mw,
        cast(publish_time at time zone 'UTC' as timestamp) as publish_time_utc,
        _dlt_load_id,
        row_number() over (
            partition by settlement_date, settlement_period
            order by publish_time desc
        ) as revision_rank
    from {{ dlt_source('bmrs', 'bmrs__ndf') }}
    where settlement_date is not null
      and (boundary = 'N' or boundary is null)
)

select timestamp_utc, settlement_date, settlement_period, demand_mw, publish_time_utc, _dlt_load_id
from ranked
where revision_rank = 1
