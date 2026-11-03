-- The outage profile intervals of each REMIT message (dlt child table), joined to the message's current version.
select
    m.id as message_id,
    cast(o._dlt_list_idx as integer) as interval_index,
    cast(o.start_time at time zone 'UTC' as timestamp) as interval_start_utc,
    cast(o.end_time at time zone 'UTC' as timestamp) as interval_end_utc,
    cast(o.capacity as double) as available_capacity_mw,
    m._dlt_load_id
from {{ dlt_source('bmrs', 'bmrs__remit__outage_profile') }} o
join {{ dlt_source('bmrs', 'bmrs__remit') }} m on o._dlt_parent_id = m._dlt_id and m._dlt_valid_to is null
