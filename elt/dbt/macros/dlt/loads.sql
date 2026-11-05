{#
  Load-id contract (docs/architecture.md), the one definition of a pending load: a completed dlt load
  (`raw._dlt_loads.status = 0`) is pending for a tracked model (`meta.dlt_tracked`) until
  `dlt_meta.dlt_load_audit` records it for that model; with no model, until it records it for every tracked
  model. Reads tables, never views: a test or hook may run while another thread rebuilds a view.
#}
{% macro dlt_pending_load_ids_sql(model_name=none) -%}
    {%- set loads = adapter.get_relation(database=target.database, schema='raw', identifier='_dlt_loads') -%}
    {%- set audit = adapter.get_relation(database=target.database, schema='dlt_meta', identifier='dlt_load_audit') -%}
    {%- set tracked = [model_name] if model_name else dlt_tracked_models() -%}
    {%- if loads is none -%}
    select cast(null as varchar) as load_id where false
    {%- else -%}
    select l.load_id from {{ loads }} l
    where l.status = 0
    {%- if audit and tracked %}
      and (select count(distinct a.model_name) from {{ audit }} a
           where a.load_id = l.load_id
             and a.model_name in ({% for m in tracked %}'{{ m }}'{% if not loop.last %}, {% endif %}{% endfor %})) < {{ tracked | length }}
    {%- endif %}
    {%- endif %}
{%- endmacro %}

{# Predicate: `column` belongs to a load still pending for `model_name` (any tracked model when none). #}
{% macro dlt_recent(column, model_name=none) -%}
    {{ column }} in ({{ dlt_pending_load_ids_sql(model_name) }})
{%- endmacro %}

{# Incremental filter for a tracked model: rows from loads still pending for this model. #}
{% macro dlt_incremental_filter(column='_dlt_load_id') -%}
    {#- refs rendered unconditionally so dbt registers the dependencies at parse time -#}
    {%- set _ = [ref('dlt_loads'), ref('dlt_load_audit')] -%}
    {%- if is_incremental() -%}
        {{ dlt_recent(column, this.identifier) }}
    {%- else -%}
        true
    {%- endif -%}
{%- endmacro %}

{# Names of tracked models (meta.dlt_tracked) in the project. #}
{% macro dlt_tracked_models() -%}
    {%- set names = [] -%}
    {%- if execute -%}
        {%- for node in graph.nodes.values() if node.resource_type == 'model' and (node.config.meta or {}).get('dlt_tracked') -%}
            {%- do names.append(node.alias or node.name) -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(names) }}
{%- endmacro %}
