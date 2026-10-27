{{ config(unique_key='timestamp_utc') }}

-- FUELINST fuel types plus PVLive solar; other areas are in mart_generation_actual
with gb as (
    select * from {{ ref('ods_generation_actual') }}
    where source_dataset in ('FUELINST', 'PVLIVE')
),

affected as (
    select distinct timestamp_utc
    from gb
    where {{ dlt_incremental_filter('_dlt_load_id') }}
),

pivoted as (
    select
        g.timestamp_utc,
        g.settlement_date,
        g.settlement_period,
        {{ exact_sum("case when g.source_code = 'WIND' then g.generation_mw end") }} as wind_mw,
        {{ exact_sum("case when g.source_code = 'SOLAR' then g.generation_mw end") }} as solar_mw,
        {{ exact_sum("case when g.source_code = 'NUCLEAR' then g.generation_mw end") }} as nuclear_mw,
        {{ exact_sum("case when g.source_code = 'CCGT' then g.generation_mw end") }} as ccgt_gas_mw,
        {{ exact_sum("case when g.source_code = 'BIOMASS' then g.generation_mw end") }} as biomass_mw,
        {{ exact_sum("case when g.source_code in ('NPSHYD', 'PS') then g.generation_mw end") }} as hydro_mw,
        {{ exact_sum("case when g.source_code = 'COAL' then g.generation_mw end") }} as coal_mw,
        {{ exact_sum("case when g.source_code like 'INT%' then g.generation_mw end") }} as imports_mw,
        {{ exact_sum("case when g.source_code in ('OCGT', 'OIL', 'OTHER') then g.generation_mw end") }} as other_fossil_mw,
        {{ exact_sum("g.generation_mw") }} as total_generation_mw,
        count(*) as _source_rows,
        count(distinct g.source_code) as _fuel_types,
        max(g._dlt_load_id) as _last_dlt_load_id
    from gb g
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
