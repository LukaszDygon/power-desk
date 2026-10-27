{# Length in minutes of an ISO 8601 resolution such as `PT15M`, `PT60M` or `PT1H` (null otherwise). #}
{% macro iso8601_duration_minutes(expr) -%}
    case
        when {{ expr }} similar to 'PT[0-9]+M' then cast(regexp_extract({{ expr }}, '[0-9]+') as integer)
        when {{ expr }} similar to 'PT[0-9]+H' then cast(regexp_extract({{ expr }}, '[0-9]+') as integer) * 60
    end
{%- endmacro %}
