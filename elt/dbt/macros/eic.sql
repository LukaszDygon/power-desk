{#
  EIC check character (ENTSO-E EIC data exchange implementation guide, "The ENTSO-E check
  character algorithm"): characters 0-9 -> 0-9, A-Z -> 10-35, '-' -> 36; weights 16..2 over the
  first 15 characters; check value = 36 - ((sum - 1) mod 37), mapped back with the same alphabet.
  ENTSO-E permits the algorithm only for checking the validity of allocated codes, which is
  all it is used for here.
#}
{% macro eic_check_character(code_expr) -%}
    {%- set alphabet = "'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-'" -%}
    substr({{ alphabet }}, cast(36 - ((list_sum(list_transform(range(1, 16),
        i -> (strpos({{ alphabet }}, substr({{ code_expr }}, i, 1)) - 1) * (17 - i))) - 1) % 37) as integer) + 1, 1)
{%- endmacro %}

{# Version validity of an scd2 snapshot row as naive UTC timestamps, plus a current flag. #}
{% macro scd2_validity() -%}
    cast(_dlt_valid_from at time zone 'UTC' as timestamp) as valid_from,
    cast(_dlt_valid_to at time zone 'UTC' as timestamp) as valid_to,
    _dlt_valid_to is null as is_current
{%- endmacro %}
