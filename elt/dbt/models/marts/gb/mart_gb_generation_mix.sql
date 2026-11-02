{{ config(unique_key='timestamp_utc') }}

-- GB generation per 5-minute interval: each FUELINST fuel type as published by Elexon, plus PVLive solar,
-- located by their conformed technology (seeds/mappings/map_technology); other areas are in
-- mart_generation_actual. Total generation and the zero-carbon share follow NESO's Historic GB
-- Generation Mix (GENERATION, ZERO_CARBON; see the catalog definitions).
with gb as (
    select g.*, t.is_zero_carbon
    from {{ ref('ods_generation_actual') }} g
    left join {{ ref('dim_technology') }} t on t.technology_code = g.technology_code
    where g.source_dataset in ('FUELINST', 'PVLIVE')
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
        {{ exact_sum("case when g.technology_code = 'wind' then g.generation_mw end") }} as wind_mw,
        {{ exact_sum("case when g.technology_code = 'solar' then g.generation_mw end") }} as solar_mw,
        {{ exact_sum("case when g.technology_code = 'nuclear' then g.generation_mw end") }} as nuclear_mw,
        {{ exact_sum("case when g.technology_code = 'gas_ccgt' then g.generation_mw end") }} as ccgt_gas_mw,
        {{ exact_sum("case when g.technology_code = 'gas_ocgt' then g.generation_mw end") }} as ocgt_gas_mw,
        {{ exact_sum("case when g.technology_code = 'oil' then g.generation_mw end") }} as oil_mw,
        {{ exact_sum("case when g.technology_code = 'coal' then g.generation_mw end") }} as coal_mw,
        {{ exact_sum("case when g.technology_code = 'biomass' then g.generation_mw end") }} as biomass_mw,
        {{ exact_sum("case when g.technology_code = 'hydro' then g.generation_mw end") }} as hydro_mw,
        {{ exact_sum("case when g.technology_code = 'hydro_pumped_storage' then g.generation_mw end") }} as pumped_storage_mw,
        {{ exact_sum("case when g.technology_code = 'other' then g.generation_mw end") }} as other_mw,
        {{ exact_sum("case when g.technology_code = 'interconnector' then g.generation_mw end") }} as imports_mw,
        -- generation delivered: exports (negative interconnector flows) and pumping are not generation
        {{ exact_sum("greatest(g.generation_mw, 0)") }} as total_generation_mw,
        {{ exact_sum("case when g.is_zero_carbon then greatest(g.generation_mw, 0) end") }} as zero_carbon_mw,
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
    ocgt_gas_mw,
    oil_mw,
    coal_mw,
    biomass_mw,
    hydro_mw,
    pumped_storage_mw,
    other_mw,
    imports_mw,
    total_generation_mw,
    zero_carbon_mw,
    round(zero_carbon_mw / nullif(total_generation_mw, 0) * 100.0, 1) as zero_carbon_share_pct,
    _source_rows,
    _fuel_types,
    _last_dlt_load_id,
    '{{ invocation_id }}' as _dbt_invocation_id,
    now() as _dbt_updated_at
from pivoted
