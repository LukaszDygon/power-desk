{#
  ENTSO-E PsrType code (seed `entsoe_psr_types`) of a production type name as the Transparency Platform
  displays it (e.g. `Fossil Gas` -> `B04`); null for a name not in the code list. Every source publishing
  the names (ENTSO-E exports, Elexon REMIT fuel types) derives the code here; `map_technology` maps the code.
#}
{% macro entsoe_psr_type(production_type_expr) -%}
    (select p.psr_type from {{ ref('entsoe_psr_types') }} p where p.production_type = {{ production_type_expr }})
{%- endmacro %}
