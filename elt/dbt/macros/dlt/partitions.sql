{#
  An ODS branch's input: `relation` (a staging model with _dlt_load_id), narrowed on an incremental build to
  the partitions holding a row of a pending load, so the branch transforms whole partitions only and the
  model replaces them (delete+insert on its unique key). A partition is `keys` plus the hour of
  timestamp_utc (time series: first narrowed to their time range, pruned by the table's min/max
  statistics), or `keys` alone with `hourly=false` (e.g. a REMIT event, every message of an mRID). A full
  build reads every row.
#}
{% macro pending_partitions(relation, keys=[], hourly=true) -%}
    {#- refs rendered unconditionally so dbt registers the dependencies at parse time -#}
    {%- set _ = [ref('dlt_loads'), ref('dlt_load_audit')] -%}
    {%- if is_incremental() -%}
        {%- set columns = keys + (["time_bucket(interval '1 hour', timestamp_utc)"] if hourly else []) -%}
        (with pending as (
            select distinct {% for column in columns %}{{ column }} as _key_{{ loop.index }}{{ ', ' if not loop.last }}{% endfor %}
            from {{ relation }}
            where {{ dlt_recent('_dlt_load_id', this.identifier) }}
        )
        select * from {{ relation }}
        where
            {%- if hourly %}
            timestamp_utc >= (select min(_key_{{ columns | length }}) from pending)
            and timestamp_utc < (select max(_key_{{ columns | length }}) from pending) + interval 1 hour and
            {%- endif %}
            ({{ columns | join(', ') }})
                in (select {% for column in columns %}_key_{{ loop.index }}{{ ', ' if not loop.last }}{% endfor %} from pending))
    {%- else -%}
        {{ relation }}
    {%- endif -%}
{%- endmacro %}
