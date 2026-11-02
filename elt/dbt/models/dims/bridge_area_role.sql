with roles as (
    select area_eic_code, valid_from, valid_to, is_current, unnest(roles) as role
    from {{ ref('dim_area') }}
)
select r.*, f.role_definition
from roles r
left join {{ ref('stg_entsoe_eic__functions') }} f
    on f.role = r.role and f.eic_type = 'Y' and f.market = 'Electricity' and f.is_current
