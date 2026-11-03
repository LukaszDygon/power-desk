{#
  Pre-hook of an incremental model (strategy `append`) that rebuilds whole groups: deletes the rows whose
  `column` is in `touched_sql` (the groups pending loads touched), so the model then appends their rebuilt
  rows. A group left without rows is removed too, which `delete+insert` misses: it deletes only the keys of
  the rows it inserts. REMIT needs it, since a revision can shorten, withdraw or open-end an event.
#}
{% macro delete_touched(column, touched_sql) -%}
    {%- if is_incremental() -%}
        delete from {{ this }} where {{ column }} in ({{ touched_sql }})
    {%- else -%}
        select 1
    {%- endif -%}
{%- endmacro %}

{# REMIT events (mRID) with a message in a load pending for the model being built. #}
{% macro remit_touched_events(relation) -%}
    select distinct mrid from {{ relation }} where {{ dlt_recent('_dlt_load_id', this.identifier) }}
{%- endmacro %}

{#
  The hours any revision of a touched REMIT event spans (`relation`: ods_unavailability, every revision), so
  the hours a revision moved an event out of are rebuilt as well.
#}
{% macro remit_touched_hours(relation) -%}
    select distinct unnest(generate_series(
        time_bucket(interval 1 hour, timestamp_utc),
        timestamp_utc + to_microseconds(cast(round(interval_minutes * 60e6) as bigint)) - interval 1 microsecond,
        interval 1 hour
    )) as timestamp_utc
    from {{ relation }}
    where interval_minutes > 0 and mrid in ({{ remit_touched_events(relation) }})
{%- endmacro %}
