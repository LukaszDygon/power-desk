{#
  Completeness at a fixed UTC grain: every `interval` bucket from `start_date` (default:
  var backfill_start_date) to the latest elapsed bucket present in the model exists,
  optionally for each value of `partition_column` found in `partitions_relation`.
  Use for sources keyed by UTC intervals (hourly forecasts, 15/30/60-minute MTUs);
  local settlement days use `no_missing_settlement_periods`.

  Scoped runs check from the earliest bucket touched by pending loads; dlt_scope=all
  checks the full range. Gaps after the latest loaded bucket are left to freshness checks.
#}
{% test no_missing_intervals(
    model,
    column_name,
    interval='1 hour',
    start_date=none,
    partition_column=none,
    partitions_relation=none,
    partitions_column=none,
    partitions_where='true'
) %}
{#- Warn on scheduled runs so a gap never blocks mart builds; fail the nightly full-scope run. -#}
{{ config(meta={'dlt_unscoped': true}, severity=('error' if var('dlt_scope', 'recent') == 'all' else 'warn')) }}
{%- set recent = dlt_scope_filter_for(model) -%}
{%- set start = start_date or var('backfill_start_date') -%}
{%- set bucket = "time_bucket(interval '" ~ interval ~ "', cast(" ~ column_name ~ " as timestamp))" %}

with present as (
    select distinct
        {{ bucket }} as bucket
        {%- if partition_column %}, {{ partition_column }} as partition_value{% endif %}
    from {{ model }}
),
bounds as (
    select
        {%- if recent %}
        -- null (nothing to check) when no pending load touched the model; greatest() ignores nulls
        case when recent_min is not null then greatest(cast('{{ start }}' as timestamp), recent_min) end as first_bucket,
        {%- else %}
        cast('{{ start }}' as timestamp) as first_bucket,
        {%- endif %}
        least(
            (select max(bucket) from present),
            time_bucket(interval '{{ interval }}', cast(now() at time zone 'UTC' as timestamp)) - interval '{{ interval }}'
        ) as last_bucket
    {%- if recent %}
    from (select min({{ bucket }}) as recent_min from {{ model }} where {{ recent }})
    {%- endif %}
),
expected as (
    select t.bucket
    from bounds, range(first_bucket, last_bucket + interval '{{ interval }}', interval '{{ interval }}') t(bucket)
)
{%- if partition_column %},
partitions as (
    select distinct {{ partitions_column or partition_column }} as partition_value from {{ partitions_relation }} where {{ partitions_where }}
)
{%- endif %}

select e.bucket{% if partition_column %}, pt.partition_value as {{ partition_column }}{% endif %}
from expected e
{%- if partition_column %}
cross join partitions pt
{%- endif %}
left join present p
    on p.bucket = e.bucket
   {%- if partition_column %} and p.partition_value = pt.partition_value{% endif %}
where p.bucket is null
{% endtest %}
