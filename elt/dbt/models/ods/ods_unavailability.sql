{{ config(
    incremental_strategy='append',
    pre_hook="{{ delete_touched('mrid', remit_touched_events(ref('stg_bmrs__remit'))) }}"
) }}

-- Unavailability of electricity facilities from REMIT messages, every revision: one row per message and
-- interval, the outage profile's intervals where the message publishes one, else the event period. A build
-- rebuilds every event (mRID) a pending load touched, all its revisions, since a revision can shorten or
-- withdraw an event (macros/dlt/replace_touched.sql).
with touched as (
    select distinct mrid from {{ ref('stg_bmrs__remit') }} where {{ dlt_incremental_filter('_dlt_load_id') }}
),

messages as (
    select m.*
    from {{ ref('stg_bmrs__remit') }} m
    semi join touched using (mrid)
    where m.message_type = 'UnavailabilitiesOfElectricityFacilities'
),

profiles as (
    select p.*
    from {{ ref('stg_bmrs__remit__outage_profile') }} p
    semi join messages using (message_id)
),

intervals as (
    select message_id, interval_index, interval_start_utc as start_utc, interval_end_utc as end_utc,
        available_capacity_mw
    from profiles
    union all
    select message_id, cast(null as integer), event_start_utc, event_end_utc, available_capacity_mw
    from messages m
    where not exists (select 1 from profiles p where p.message_id = m.message_id)
)

select
    i.start_utc as timestamp_utc,
    date_diff('second', i.start_utc, i.end_utc) / 60.0 as interval_minutes,
    m.bidding_zone as area_eic_code,
    t.technology_code,
    r.resource_code,
    m.unavailable_capacity_mw,
    i.available_capacity_mw,
    m.installed_capacity_mw,
    m.mrid,
    m.revision_number,
    m.message_id,
    i.interval_index,
    m.is_latest_revision,
    m.event_status,
    m.event_type,
    m.unavailability_type,
    m.event_start_utc,
    m.event_end_utc,
    m.reason,
    m.affected_unit_eic,
    m.publish_time_utc,
    'REMIT' as source_dataset,
    m.asset_id as source_code,
    m._dlt_load_id
from intervals i
join messages m using (message_id)
left join {{ ref('map_technology') }} t on t.source_dataset = 'ENTSOE_PSR' and t.source_code = m.psr_type
left join {{ ref('dim_resource') }} r
    on r.resource_code = m.asset_id and r.resource_scheme = 'BM_UNIT' and r.is_current
