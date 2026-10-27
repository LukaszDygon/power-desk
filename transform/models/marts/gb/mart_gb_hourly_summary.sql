{{ config(unique_key='hour_utc') }}

with affected as (
    select distinct date_trunc('hour', timestamp_utc) as hour_utc
    from {{ ref('mart_gb_generation_mix') }}
    where {{ dlt_incremental_filter('_last_dlt_load_id') }}
    union
    select distinct date_trunc('hour', timestamp_utc) as hour_utc
    from {{ ref('mart_gb_demand_vs_forecast') }}
    where {{ dlt_incremental_filter('_last_dlt_load_id') }}
),

generation as (
    select g.*
    from {{ ref('mart_gb_generation_mix') }} g
    inner join affected a on a.hour_utc = date_trunc('hour', g.timestamp_utc)
)

select
    date_trunc('hour', g.timestamp_utc) as hour_utc,
    cast(date_trunc('hour', g.timestamp_utc) as date) as date_utc,
    {{ exact_avg('d.actual_demand_mw') }} as avg_demand_mw,
    {{ exact_avg('d.forecast_demand_mw') }} as avg_forecast_demand_mw,
    {{ exact_avg('g.total_generation_mw') }} as avg_generation_mw,
    {{ exact_avg('g.wind_mw') }} as avg_wind_mw,
    {{ exact_avg('g.solar_mw') }} as avg_solar_mw,
    {{ exact_avg('g.nuclear_mw') }} as avg_nuclear_mw,
    {{ exact_avg('g.ccgt_gas_mw') }} as avg_gas_mw,
    {{ exact_avg('g.zero_carbon_share_pct') }} as avg_zero_carbon_share_pct,
    round(max(d.actual_demand_mw), 1) as peak_demand_mw,
    round(min(d.actual_demand_mw), 1) as min_demand_mw,
    count(*) as _source_rows,
    greatest(max(g._last_dlt_load_id), max(d._last_dlt_load_id)) as _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from generation g
left join {{ ref('mart_gb_demand_vs_forecast') }} d
    on d.timestamp_utc = g.timestamp_utc
group by date_trunc('hour', g.timestamp_utc)
