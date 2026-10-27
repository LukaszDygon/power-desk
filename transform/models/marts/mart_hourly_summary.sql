{{ config(unique_key='hour_utc') }}

with affected as (
    select distinct date_trunc('hour', timestamp_utc) as hour_utc
    from {{ ref('mart_generation_mix') }}
    where {{ dlt_incremental_filter('_last_dlt_load_id') }}
    union
    select distinct date_trunc('hour', timestamp_utc) as hour_utc
    from {{ ref('mart_demand_vs_forecast') }}
    where {{ dlt_incremental_filter('_last_dlt_load_id') }}
),

generation as (
    select g.*
    from {{ ref('mart_generation_mix') }} g
    inner join affected a on a.hour_utc = date_trunc('hour', g.timestamp_utc)
)

select
    date_trunc('hour', g.timestamp_utc) as hour_utc,
    cast(date_trunc('hour', g.timestamp_utc) as date) as date_utc,
    round(avg(d.actual_demand_mw), 1) as avg_demand_mw,
    round(avg(d.forecast_demand_mw), 1) as avg_forecast_demand_mw,
    round(avg(g.total_generation_mw), 1) as avg_generation_mw,
    round(avg(g.wind_mw), 1) as avg_wind_mw,
    round(avg(g.solar_mw), 1) as avg_solar_mw,
    round(avg(g.nuclear_mw), 1) as avg_nuclear_mw,
    round(avg(g.ccgt_gas_mw), 1) as avg_gas_mw,
    round(avg(g.clean_share_pct), 1) as avg_clean_share_pct,
    round(max(d.actual_demand_mw), 1) as peak_demand_mw,
    round(min(d.actual_demand_mw), 1) as min_demand_mw,
    count(*) as _source_rows,
    greatest(max(g._last_dlt_load_id), max(d._last_dlt_load_id)) as _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from generation g
left join {{ ref('mart_demand_vs_forecast') }} d
    on d.timestamp_utc = g.timestamp_utc
group by date_trunc('hour', g.timestamp_utc)
