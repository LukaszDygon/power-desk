{# dlt load-id contract (docs/architecture.md): pending loads, incremental filters, test scoping, audit. #}

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

{#
  Test scoping. Returns the recent-rows predicate for the node a test is attached to,
  or none when the test must see the whole relation (dlt_scope = all, an unscoped
  test, or a node without meta.dlt_recent_column).
#}
{% macro dlt_test_scope_filter(relation) -%}
    {%- set scoped = none -%}
    {%- set test_meta = config.get('meta') or {} -%}
    {%- if execute and var('dlt_scope', 'recent') != 'all' and not test_meta.get('dlt_unscoped') -%}
        {%- set scoped = dlt_scope_filter_for(relation) -%}
    {%- endif -%}
    {{ return(scoped) }}
{%- endmacro %}

{# Recent-rows predicate for `relation` regardless of test config (used by key-scoped tests). #}
{% macro dlt_scope_filter_for(relation) -%}
    {#- namespace: plain `set` inside a for loop does not survive the loop -#}
    {%- set ns = namespace(predicate=none) -%}
    {%- if execute and var('dlt_scope', 'recent') != 'all' -%}
        {%- for unique_id in model.depends_on.nodes -%}
            {%- set node = graph.nodes.get(unique_id) or graph.sources.get(unique_id) -%}
            {%- if node and (node.identifier or node.alias or node.name) == relation.identifier -%}
                {%- set meta = node.config.meta or {} -%}
                {%- if meta.get('dlt_recent_column') -%}
                    {%- set model_name = (node.alias or node.name) if meta.get('dlt_tracked') else none -%}
                    {%- set ns.predicate = dlt_recent(meta.get('dlt_recent_column'), model_name, use_ref=false) -%}
                {%- endif -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(ns.predicate) }}
{%- endmacro %}

{# Generic tests on tracked/raw/ods nodes only look at rows from pending loads. #}
{% macro get_where_subquery(relation) -%}
    {%- set filters = [] -%}
    {%- set where = config.get('where') -%}
    {%- if where -%}{%- do filters.append(where) -%}{%- endif -%}
    {%- set scope = dlt_test_scope_filter(relation) -%}
    {%- if scope -%}{%- do filters.append(scope) -%}{%- endif -%}
    {%- if filters -%}
        {%- set filtered -%}
            (select * from {{ relation }} where {{ filters | join(' and ') }}) dbt_subquery
        {%- endset -%}
        {%- do return(filtered) -%}
    {%- else -%}
        {%- do return(relation) -%}
    {%- endif -%}
{%- endmacro %}

{#
  on-run-end: record (load_id, model) for every tracked model that built successfully
  and has no failing/erroring test in this invocation.
#}
{% macro dlt_mark_loads_processed(results) %}
    {%- if not execute -%}{{ return('') }}{%- endif -%}
    {%- set audit = adapter.get_relation(database=target.database, schema='dlt_meta', identifier='dlt_load_audit') -%}
    {%- if audit is none -%}{{ return('') }}{%- endif -%}

    {%- set failed = [] -%}
    {%- for r in results if r.node.resource_type in ('test', 'unit_test') and r.status in ('fail', 'error') -%}
        {%- for dep in r.node.depends_on.nodes -%}{%- do failed.append(dep) -%}{%- endfor -%}
    {%- endfor -%}

    {%- set done = [] -%}
    {%- for r in results if r.node.resource_type == 'model' and r.status == 'success'
            and (r.node.config.meta or {}).get('dlt_tracked') and r.node.unique_id not in failed -%}
        {%- do done.append(r.node.alias or r.node.name) -%}
    {%- endfor -%}

    {%- if done | length == 0 -%}{{ return('') }}{%- endif -%}
    {%- do log('dlt: marking pending loads processed for ' ~ (done | join(', ')), info=true) -%}

    insert into {{ audit }} (load_id, model_name, dbt_invocation_id, orchestrator_run_id, processed_at)
    {% for model_name in done %}
    select p.load_id, '{{ model_name }}', '{{ invocation_id }}', '{{ var("orchestrator_run_id", "") }}', now()
    from ({{ dlt_pending_load_ids_sql(model_name, use_ref=false) }}) p
    where p.load_id not in (select load_id from {{ audit }} where model_name = '{{ model_name }}')
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
{% endmacro %}
