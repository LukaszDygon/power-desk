{#
  A dlt raw table, as `source()`. Before the table's first load: an empty relation with the
  source's documented columns, so entities unioning several sources build from the sources
  loaded so far. Every ingest run rebuilds the views, picking the table up once it exists.
#}
{% macro dlt_source(source_name, table_name) -%}
    {%- set relation = source(source_name, table_name) -%}
    {%- if execute and load_relation(relation) is none -%}
        {%- set node = graph.sources.values() | selectattr('source_name', 'equalto', source_name)
                                              | selectattr('name', 'equalto', table_name) | list | first -%}
        (select
            {%- for name, column in node.columns.items() %}
            cast(null as {{ (column.config.meta or column.meta or {}).get('dlt_data_type') or 'varchar' }}) as {{ adapter.quote(name) }}{{ ',' if not loop.last }}
            {%- endfor %}
        where false)
    {%- else -%}
        {{ relation }}
    {%- endif -%}
{%- endmacro %}
