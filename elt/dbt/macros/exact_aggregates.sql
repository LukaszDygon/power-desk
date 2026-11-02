{#
  Sums and means rounded to 0.1, computed in DECIMAL: double aggregates depend on the
  (parallel) summation order, which flips values on a rounding boundary between builds.
#}
{% macro exact_sum(expr) -%}
    cast(round(coalesce(sum(cast({{ expr }} as decimal(18, 3))), 0), 1) as double)
{%- endmacro %}

{% macro exact_avg(expr) -%}
    cast(round(avg(cast({{ expr }} as decimal(18, 3))), 1) as double)
{%- endmacro %}
