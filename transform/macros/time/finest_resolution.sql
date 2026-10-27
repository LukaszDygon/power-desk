{#
  QUALIFY clause keeping, per series and hour, only rows at the finest resolution published.
  A publisher changing its market time unit publishes the overlap at both resolutions; keeping
  both would count those hours twice.
#}
{% macro keep_finest_resolution(series) -%}
    qualify interval_minutes = min(interval_minutes) over (
        partition by {{ series | join(', ') }}, time_bucket(interval '1 hour', timestamp_utc)
    )
{%- endmacro %}
