{# Generic tests read only rows of pending loads, unless `dlt_scope = all` or the test is unscoped. #}

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
                    {%- set ns.predicate = dlt_recent(meta.get('dlt_recent_column'), model_name) -%}
                {%- endif -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(ns.predicate) }}
{%- endmacro %}

{#
  dbt's hook for the relation a generic test reads (`where` config): narrowed to the rows of pending loads
  (`dlt_test_scope_filter`). A raw table before its first load reads as `dlt_source` does, empty, so its tests
  pass until it is loaded.
#}
{% macro get_where_subquery(relation) -%}
    {%- set filters = [] -%}
    {%- set where = config.get('where') -%}
    {%- if where -%}{%- do filters.append(where) -%}{%- endif -%}
    {%- set scope = dlt_test_scope_filter(relation) -%}
    {%- if scope -%}{%- do filters.append(scope) -%}{%- endif -%}
    {%- set source = (graph.sources.values() | selectattr('identifier', 'equalto', relation.identifier)
                                             | selectattr('schema', 'equalto', relation.schema) | list | first)
                     if execute else none -%}
    {%- if source and load_relation(relation) is none -%}
        {%- do return('(select * from ' ~ dlt_source(source.source_name, source.name) ~ ') dbt_subquery') -%}
    {%- elif filters -%}
        {%- set filtered -%}
            (select * from {{ relation }} where {{ filters | join(' and ') }}) dbt_subquery
        {%- endset -%}
        {%- do return(filtered) -%}
    {%- else -%}
        {%- do return(relation) -%}
    {%- endif -%}
{%- endmacro %}
