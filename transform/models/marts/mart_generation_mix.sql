{{ config(unique_key='timestamp_utc') }}

with affected as (
    select distinct timestamp_utc
    from {{ ref('ods_generation_actual') }}
    where {{ dlt_incremental_filter('_dlt_load_id') }}
),

pivoted as (
    select
        g.timestamp_utc,
        g.settlement_date,
        g.settlement_period,
        round(coalesce(sum(case when g.fuel_type = 'WIND' then g.generation_mw end), 0), 1) as wind_mw,
        round(coalesce(sum(case when g.fuel_type = 'SOLAR' then g.generation_mw end), 0), 1) as solar_mw,
        round(coalesce(sum(case when g.fuel_type = 'NUCLEAR' then g.generation_mw end), 0), 1) as nuclear_mw,
        round(coalesce(sum(case when g.fuel_type = 'CCGT' then g.generation_mw end), 0), 1) as ccgt_gas_mw,
        round(coalesce(sum(case when g.fuel_type = 'BIOMASS' then g.generation_mw end), 0), 1) as biomass_mw,
        round(coalesce(sum(case when g.fuel_type in ('NPSHYD', 'PS') then g.generation_mw end), 0), 1) as hydro_mw,
        round(coalesce(sum(case when g.fuel_type = 'COAL' then g.generation_mw end), 0), 1) as coal_mw,
        round(coalesce(sum(case when g.fuel_type like 'INT%' then g.generation_mw end), 0), 1) as imports_mw,
        round(coalesce(sum(case when g.fuel_type in ('OCGT', 'OIL', 'OTHER') then g.generation_mw end), 0), 1) as other_fossil_mw,
        round(coalesce(sum(g.generation_mw), 0), 1) as total_generation_mw,
        count(*) as _source_rows,
        count(distinct g.fuel_type) as _fuel_types,
        max(g._dlt_load_id) as _last_dlt_load_id
    from {{ ref('ods_generation_actual') }} g
    inner join affected a on a.timestamp_utc = g.timestamp_utc
    group by g.timestamp_utc, g.settlement_date, g.settlement_period
)

select
    timestamp_utc,
    settlement_date,
    settlement_period,
    wind_mw,
    solar_mw,
    nuclear_mw,
    ccgt_gas_mw,
    biomass_mw,
    hydro_mw,
    coal_mw,
    imports_mw,
    other_fossil_mw,
    total_generation_mw,
    round(
        case
            when total_generation_mw > 0
            then ((wind_mw + solar_mw + nuclear_mw + biomass_mw + hydro_mw) / total_generation_mw) * 100.0
            else 0
        end,
        1
    ) as clean_share_pct,
    _source_rows,
    _fuel_types,
    _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from pivoted
