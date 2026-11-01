{#
  Length in minutes of an ISO 8601 resolution such as `PT15M`, `PT60M` or `PT1H` (null otherwise).
  With `start_utc` (the period's start), also calendar resolutions starting at the area's local
  midnight: `P<n>D` as n days of 1440 minutes and `P1M` as the days of the local month (local midnight
  lies within 12 hours of UTC midnight); clock-change days count 1440 minutes.
#}
{% macro iso8601_duration_minutes(expr, start_utc=none) -%}
    case
        when {{ expr }} similar to 'PT[0-9]+M' then cast(regexp_extract({{ expr }}, '[0-9]+') as integer)
        when {{ expr }} similar to 'PT[0-9]+H' then cast(regexp_extract({{ expr }}, '[0-9]+') as integer) * 60
        {%- if start_utc %}
        when {{ expr }} similar to 'P[0-9]+D' then cast(regexp_extract({{ expr }}, '[0-9]+') as integer) * 1440
        when {{ expr }} = 'P1M' then day(last_day({{ start_utc }} + interval 12 hour)) * 1440
        {%- endif %}
    end
{%- endmacro %}
