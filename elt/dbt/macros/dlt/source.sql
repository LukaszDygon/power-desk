{#
  A dlt raw table, as `source()`. Before the table's first load: an empty relation with the
  source's documented columns, so entities unioning several sources build from the sources
  loaded so far. Before a documented column's first value (dlt creates a column once a value
  arrives, e.g. a field the publisher rarely fills): the table with that column as null. Every
  ingest run rebuilds the views, picking the table and its columns up once they exist.
#}
{% macro dlt_source(source_name, table_name) -%}
    {%- set relation = source(source_name, table_name) -%}
    {%- if not execute -%}
        {{ relation }}
    {%- else -%}
        {%- set node = graph.sources.values() | selectattr('source_name', 'equalto', source_name)
                                              | selectattr('name', 'equalto', table_name) | list | first -%}
        {%- set existing = load_relation(relation) -%}
        {%- set loaded = adapter.get_columns_in_relation(existing) | map(attribute='name') | map('lower') | list if existing else [] -%}
        {%- set missing = [] -%}
        {%- for name, column in node.columns.items() if name | lower not in loaded -%}
            {%- do missing.append((name, (column.config.meta or column.meta or {}).get('dlt_data_type') or 'varchar')) -%}
        {%- endfor -%}
        {%- if existing is none -%}
        (select
            {%- for name, data_type in missing %}
            cast(null as {{ data_type }}) as {{ adapter.quote(name) }}{{ ',' if not loop.last }}
            {%- endfor %}
        where false)
        {%- elif missing -%}
        (select *
            {%- for name, data_type in missing %},
            cast(null as {{ data_type }}) as {{ adapter.quote(name) }}
            {%- endfor %}
        from {{ relation }})
        {%- else -%}
        {{ relation }}
        {%- endif -%}
    {%- endif -%}
{%- endmacro %}
