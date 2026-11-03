-- Resources in their publishers' own schemes, one row per version: ENTSO-E resource objects by EIC (object
-- type W) and Elexon's BM Units by BM Unit Id. Each source joins on its own scheme; `bridge_resource_eic`
-- relates a BM Unit to the EICs Elexon lists for it, where it lists any.
with eic_resources as (
    select
        eic_code as resource_code,
        'EIC' as resource_scheme,
        display_name,
        long_name,
        country_code,
        roles,
        parent_eic_code as parent_resource_code,
        responsible_party_eic_code,
        cast(null as varchar) as technology_code,
        cast(null as varchar) as national_grid_bm_unit,
        cast(null as varchar) as bm_unit_type,
        cast(null as varchar) as lead_party_name,
        cast(null as double) as generation_capacity_mw,
        cast(null as double) as demand_capacity_mw,
        valid_from,
        valid_to,
        is_current
    from {{ ref('dim_eic_code') }}
    where eic_type = 'W'
),

-- Elexon lists a unit once per EIC it holds (e.g. two for WLNYO-4): one row per unit and version
bm_units as (
    select distinct
        u.elexon_bm_unit as resource_code,
        'BM_UNIT' as resource_scheme,
        u.bm_unit_name as display_name,
        cast(null as varchar) as long_name,
        cast(null as varchar) as country_code,
        cast(null as varchar[]) as roles,
        cast(null as varchar) as parent_resource_code,
        cast(null as varchar) as responsible_party_eic_code,
        t.technology_code,
        u.national_grid_bm_unit,
        u.bm_unit_type,
        u.lead_party_name,
        u.generation_capacity_mw,
        u.demand_capacity_mw,
        u.valid_from,
        u.valid_to,
        u.is_current
    from {{ ref('stg_bmrs__bmunits') }} u
    left join {{ ref('map_technology') }} t on t.source_dataset = 'BMUNITS' and t.source_code = u.fuel_type
    where u.elexon_bm_unit is not null
)

select * from eic_resources
union all
select * from bm_units
