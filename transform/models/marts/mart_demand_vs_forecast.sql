{{ config(unique_key=['settlement_date', 'settlement_period']) }}

with affected as (
    select settlement_date, settlement_period
    from {{ ref('ods_demand_actual') }}
    where {{ dlt_incremental_filter('_dlt_load_id') }}
    union
    select settlement_date, settlement_period
    from {{ ref('ods_demand_forecast') }}
    where {{ dlt_incremental_filter('_dlt_load_id') }}
),

actual as (
    select a.*
    from {{ ref('ods_demand_actual') }} a
    inner join affected using (settlement_date, settlement_period)
),

forecast as (
    select f.*
    from {{ ref('ods_demand_forecast') }} f
    inner join affected using (settlement_date, settlement_period)
)

select
    coalesce(a.timestamp_utc, f.timestamp_utc) as timestamp_utc,
    coalesce(a.settlement_date, f.settlement_date) as settlement_date,
    coalesce(a.settlement_period, f.settlement_period) as settlement_period,
    a.national_demand_mw as actual_demand_mw,
    f.forecast_demand_mw as forecast_demand_mw,
    round(a.national_demand_mw - f.forecast_demand_mw, 1) as delta_mw,
    round(
        case
            when a.national_demand_mw is not null and a.national_demand_mw > 0
            then (abs(a.national_demand_mw - f.forecast_demand_mw) / a.national_demand_mw) * 100.0
        end,
        2
    ) as absolute_error_pct,
    (case when a.settlement_date is not null then 1 else 0 end)
        + (case when f.settlement_date is not null then 1 else 0 end) as _source_rows,
    greatest(a._dlt_load_id, f._dlt_load_id) as _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from actual a
full outer join forecast f
    on a.settlement_date = f.settlement_date
   and a.settlement_period = f.settlement_period
