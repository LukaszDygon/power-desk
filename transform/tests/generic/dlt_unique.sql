{#
  Duplication guard on a key. Scoped runs check every key touched by pending loads
  against the WHOLE relation, so a recent row duplicating an old one is caught
  (a plain row-scoped unique test would miss it).
#}
{% test dlt_unique(model, columns) %}
{{ config(meta={'dlt_unscoped': true}) }}
{%- set recent = dlt_scope_filter_for(model) -%}
{%- set key = columns | join(', ') %}

with duplicates as (
    select {{ key }}, count(*) as n_rows
    from {{ model }}
    group by {{ key }}
    having count(*) > 1
)
select d.*
from duplicates d
{%- if recent %}
where exists (
    select 1 from {{ model }} r
    where {{ recent }}
    {%- for c in columns %}
      and r.{{ c }} is not distinct from d.{{ c }}
    {%- endfor %}
)
{%- endif %}
{% endtest %}
