{#
  An ODS branch's input: `relation` (a staging model with timestamp_utc and _dlt_load_id), narrowed on an
  incremental build to the partitions (`keys`, hour of timestamp_utc) holding a row of a pending load: first
  to their time range (pruned by the table's min/max statistics), then to the exact partitions. The branch
  then transforms whole partitions only, and the model replaces them (unique key: timestamp, area, source
  dataset). A full build reads every row.
#}
{% macro pending_partitions(relation, keys=[]) -%}
    {#- refs rendered unconditionally so dbt registers the dependencies at parse time -#}
    {%- set _ = [ref('dlt_loads'), ref('dlt_load_audit')] -%}
    {%- if is_incremental() -%}
        {%- set hour = "time_bucket(interval '1 hour', timestamp_utc)" -%}
        (with pending as (
            select distinct {% for key in keys %}{{ key }}, {% endfor %}{{ hour }} as hour_utc
            from {{ relation }}
            where {{ dlt_recent('_dlt_load_id', this.identifier) }}
        )
        select * from {{ relation }}
        where timestamp_utc >= (select min(hour_utc) from pending)
          and timestamp_utc < (select max(hour_utc) from pending) + interval 1 hour
          and ({% for key in keys %}{{ key }}, {% endfor %}{{ hour }})
              in (select {% for key in keys %}{{ key }}, {% endfor %}hour_utc from pending))
    {%- else -%}
        {{ relation }}
    {%- endif -%}
{%- endmacro %}
