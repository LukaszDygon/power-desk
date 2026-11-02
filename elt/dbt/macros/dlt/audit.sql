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
