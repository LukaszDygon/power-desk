{# Load-id contract (docs/architecture.md): which dlt loads a run processes, and incremental filters. #}

{#
  SELECT returning the load ids to process: the explicit var, else the loads pending for
  `model_name` (or for any tracked model). Models resolve through refs; tests and hooks read
  tables only, since views may be rebuilt by another thread while they run.
#}
{% macro dlt_pending_load_ids_sql(model_name=none, use_ref=true) -%}
    {%- set ids = var('dlt_load_ids', none) -%}
    {%- if ids is not none -%}
        select unnest(cast([{% for i in ids %}'{{ i }}'{% if not loop.last %}, {% endif %}{% endfor %}] as varchar[])) as load_id
    {%- elif use_ref and model_name -%}
        select l.load_id from {{ ref('dlt_loads') }} l
        where l.status = 0
          and l.load_id not in (select a.load_id from {{ ref('dlt_load_audit') }} a where a.model_name = '{{ model_name }}')
    {%- elif use_ref -%}
        select load_id from {{ ref('dlt_pending_loads') }}
    {%- else -%}
        {%- set loads = api.Relation.create(database=target.database, schema='raw', identifier='_dlt_loads') -%}
        {%- set audit = adapter.get_relation(database=target.database, schema='dlt_meta', identifier='dlt_load_audit') -%}
        {%- set tracked = [model_name] if model_name else dlt_tracked_models() -%}
        select l.load_id from {{ loads }} l
        where l.status = 0
        {%- if audit and tracked %}
          and (select count(distinct a.model_name) from {{ audit }} a
               where a.load_id = l.load_id
                 and a.model_name in ({% for m in tracked %}'{{ m }}'{% if not loop.last %}, {% endif %}{% endfor %})) < {{ tracked | length }}
        {%- endif %}
    {%- endif -%}
{%- endmacro %}

{# Predicate: `column` belongs to a load this run must process. #}
{% macro dlt_recent(column, model_name=none, use_ref=true) -%}
    {{ column }} in ({{ dlt_pending_load_ids_sql(model_name, use_ref) }})
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
