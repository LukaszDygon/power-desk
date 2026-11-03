{{ config(
    incremental_strategy='append',
    pre_hook="{{ delete_touched('mrid', remit_touched_events(ref('ods_unavailability'))) }}"
) }}

-- Each REMIT event's latest revision on an hourly spine: one row per event, unit and hour its intervals cover,
-- capacities time-weighted over the covered seconds. Open-ended events (no event stop) and instants are not
-- placed. A build rebuilds every event a pending load touched (macros/dlt/replace_touched.sql), since
-- hourly_series rebuilds only the hours new rows cover and a revision can shorten or withdraw an event.
with touched as (
    select distinct mrid from {{ ref('ods_unavailability') }} where {{ dlt_incremental_filter('_dlt_load_id') }}
),

intervals as (
    select
        o.*,
        o.timestamp_utc + to_microseconds(cast(round(o.interval_minutes * 60e6) as bigint)) as end_utc
    from {{ ref('ods_unavailability') }} o
    semi join touched using (mrid)
    where o.is_latest_revision and o.interval_minutes > 0
),

hourly as (
    select
        h.hour_utc,
        i.*,
        epoch(least(i.end_utc, h.hour_utc + interval 1 hour) - greatest(i.timestamp_utc, h.hour_utc)) as seconds
    from intervals i,
        unnest(generate_series(
            time_bucket(interval 1 hour, i.timestamp_utc), i.end_utc - interval 1 microsecond, interval 1 hour
        )) as h(hour_utc)
)

select
    hour_utc as timestamp_utc,
    area_eic_code,
    technology_code,
    resource_code,
    sum(unavailable_capacity_mw * seconds) / sum(seconds) as unavailable_capacity_mw,
    sum(available_capacity_mw * seconds) / sum(seconds) filter (where available_capacity_mw is not null)
        as available_capacity_mw,
    least(sum(seconds), 3600) / 3600 as coverage,
    event_status,
    event_type,
    unavailability_type,
    mrid,
    revision_number,
    source_dataset,
    source_code,
    max(publish_time_utc) as publish_time_utc,
    max(_dlt_load_id) as _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from hourly
group by all
