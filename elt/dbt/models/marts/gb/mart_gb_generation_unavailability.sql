{{ config(
    incremental_strategy='append',
    pre_hook="{{ delete_touched('timestamp_utc', remit_touched_hours(ref('ods_unavailability'))) }}"
) }}

-- Generation capacity made unavailable per hour, area, technology and type of unavailability, from the
-- production unavailability events published under REMIT (latest revisions, dismissed events excluded).
-- Unavailable capacities add up across events: each message reports only the capacity its own event makes
-- unavailable (ACER MoP, Annex VII, field 9). A build rebuilds every hour any revision of a touched event spans.
with events as (
    select m.*
    from {{ ref('mart_unavailability') }} m
    {%- if is_incremental() %}
    semi join ({{ remit_touched_hours(ref('ods_unavailability')) }}) h using (timestamp_utc)
    {%- endif %}
    where m.event_type = 'Production unavailability' and m.event_status <> 'Dismissed'
)

select
    timestamp_utc,
    area_eic_code,
    technology_code,
    unavailability_type,
    sum(unavailable_capacity_mw * coverage) as unavailable_capacity_mw,
    count(distinct mrid) as events,
    count(*) as _source_rows,
    max(_last_dlt_load_id) as _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from events
group by timestamp_utc, area_eic_code, technology_code, unavailability_type
