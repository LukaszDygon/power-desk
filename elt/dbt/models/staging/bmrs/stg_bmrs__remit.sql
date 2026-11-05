-- Every published REMIT message (raw keeps each message's current version), typed, flagged with whether it
-- is its event's latest revision: "The latest UMM published (latest UMM version) related to an event is the
-- only applicable one" (ACER MoP, Annex VII, field 1). Elexon at times republishes a revision: the latest
-- publication of the highest revision applies, once per unit listed.
with messages as (
    select
        m.id as message_id,
        m.mrid,
        cast(m.revision_number as integer) as revision_number,
        cast(m.publish_time at time zone 'UTC' as timestamp) as publish_time_utc,
        cast(m.created_time at time zone 'UTC' as timestamp) as created_time_utc,
        m.message_type,
        m.message_heading,
        m.event_type,
        m.unavailability_type,
        m.event_status,
        m.participant_id,
        m.registration_code,
        m.asset_id,
        m.asset_type,
        m.affected_unit,
        m.affected_unit_eic,
        m.affected_area,
        m.bidding_zone,
        m.fuel_type,
        {{ entsoe_psr_type('m.fuel_type') }} as psr_type,
        cast(m.normal_capacity as double) as installed_capacity_mw,
        cast(m.available_capacity as double) as available_capacity_mw,
        cast(m.unavailable_capacity as double) as unavailable_capacity_mw,
        cast(m.event_start_time at time zone 'UTC' as timestamp) as event_start_utc,
        cast(m.event_end_time at time zone 'UTC' as timestamp) as event_end_utc,
        m.duration_uncertainty,
        m.cause as reason,
        m.related_information as remarks,
        m._dlt_load_id
    from {{ dlt_source('bmrs', 'bmrs__remit') }} m
    where m._dlt_valid_to is null
)

select
    * exclude (_dlt_load_id),
    rank() over (partition by mrid order by revision_number desc, publish_time_utc desc) = 1
    and row_number() over (
        partition by mrid, revision_number, publish_time_utc, asset_id order by created_time_utc desc, message_id desc
    ) = 1 as is_latest_revision,
    _dlt_load_id
from messages
