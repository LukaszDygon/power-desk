{{ config(unique_key=['settlement_date', 'settlement_period']) }}

-- GB national demand (INDO) against its forecast (NDF); other areas are in mart_demand_actual
with indo as (
    select * from {{ ref('ods_demand_actual') }} where source_dataset = 'INDO'
),

ndf as (
    select * from {{ ref('ods_demand_forecast') }} where source_dataset = 'NDF'
),

affected as (
    select settlement_date, settlement_period from indo where {{ dlt_incremental_filter('_dlt_load_id') }}
    union
    select settlement_date, settlement_period from ndf where {{ dlt_incremental_filter('_dlt_load_id') }}
),

actual as (
    select a.* from indo a inner join affected using (settlement_date, settlement_period)
),

forecast as (
    select f.* from ndf f inner join affected using (settlement_date, settlement_period)
)

select
    coalesce(a.timestamp_utc, f.timestamp_utc) as timestamp_utc,
    coalesce(a.settlement_date, f.settlement_date) as settlement_date,
    coalesce(a.settlement_period, f.settlement_period) as settlement_period,
    a.demand_mw as actual_demand_mw,
    f.demand_mw as forecast_demand_mw,
    round(a.demand_mw - f.demand_mw, 1) as delta_mw,
    round(
        case
            when a.demand_mw is not null and a.demand_mw > 0
            then (abs(a.demand_mw - f.demand_mw) / a.demand_mw) * 100.0
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
