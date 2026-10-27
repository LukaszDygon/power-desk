with ranked as (
    select
        cast(start_time at time zone 'UTC' as timestamp) as timestamp_utc,
        cast(generation as double) as generation_mw,
        cast(publish_time at time zone 'UTC' as timestamp) as publish_time_utc,
        _dlt_load_id,
        row_number() over (partition by start_time order by publish_time desc) as revision_rank
    from {{ dlt_source('bmrs', 'bmrs__windfor') }}
    where start_time is not null
)

select timestamp_utc, generation_mw, publish_time_utc, _dlt_load_id
from ranked
where revision_rank = 1
