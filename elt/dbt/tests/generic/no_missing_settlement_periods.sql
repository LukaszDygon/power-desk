{#
  Completeness: every settlement period from `start_date` (default: var backfill_start_date)
  up to the latest elapsed period present in the model exists, using the real number of
  periods per day (46/48/50 around clock changes).

  With `partition_column` + `partitions_relation`, every period must exist for each
  partition value (e.g. every expected fuel type); `partitions_column` names the column in
  `partitions_relation` when it differs.

  Scoped runs check from the earliest settlement date touched by pending loads;
  dlt_scope=all (nightly, backfills) checks the full range. Gaps after the latest
  loaded period are left to source freshness and the cursor-lag checks.
#}
{% test no_missing_settlement_periods(
    model,
    date_column='settlement_date',
    period_column='settlement_period',
    start_date=none,
    partition_column=none,
    partitions_relation=none,
    partitions_column=none,
    partitions_where='true'
) %}
{#- Warn on scheduled runs so a gap never blocks mart builds; fail the nightly full-scope run. -#}
{{ config(meta={'dlt_unscoped': true}, severity=('error' if var('dlt_scope', 'recent') == 'all' else 'warn')) }}
{%- set recent = dlt_scope_filter_for(model) -%}
{%- set start = start_date or var('backfill_start_date') %}

with present as (
    select distinct
        cast({{ date_column }} as date) as settlement_date,
        cast({{ period_column }} as integer) as settlement_period
        {%- if partition_column %}, {{ partition_column }} as partition_value{% endif %}
    from {{ model }}
),
bounds as (
    select
        {%- if recent %}
        -- null (nothing to check) when no pending load touched the model; greatest() ignores nulls
        case when recent_min is not null then greatest(cast('{{ start }}' as date), recent_min) end as first_day,
        {%- else %}
        cast('{{ start }}' as date) as first_day,
        {%- endif %}
        least(
            (select max({{ settlement_period_to_utc('settlement_date', 'settlement_period') }}) from present),
            cast(now() at time zone 'UTC' as timestamp) - interval 30 minute
        ) as last_period_start
    {%- if recent %}
    from (select min(cast({{ date_column }} as date)) as recent_min from {{ model }} where {{ recent }})
    {%- endif %}
),
days as (
    select cast(d as date) as settlement_date
    from bounds, range(cast(first_day as timestamp), cast(last_period_start as date) + interval 1 day, interval 1 day) t(d)
),
expected as (
    select days.settlement_date, p.settlement_period
    from days, range(1, {{ settlement_periods_in_day('days.settlement_date') }} + 1) p(settlement_period)
    where {{ settlement_period_to_utc('days.settlement_date', 'p.settlement_period') }} <= (select last_period_start from bounds)
)
{%- if partition_column %},
partitions as (
    select distinct {{ partitions_column or partition_column }} as partition_value from {{ partitions_relation }} where {{ partitions_where }}
)
{%- endif %}

select e.settlement_date, e.settlement_period{% if partition_column %}, pt.partition_value as {{ partition_column }}{% endif %}
from expected e
{%- if partition_column %}
cross join partitions pt
{%- endif %}
left join present a
    on a.settlement_date = e.settlement_date
   and a.settlement_period = e.settlement_period
   {%- if partition_column %} and a.partition_value = pt.partition_value{% endif %}
where a.settlement_date is null
{% endtest %}
