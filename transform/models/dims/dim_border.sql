select
    a.area_eic_code as border_area_eic_code,
    a.display_name,
    a.long_name,
    e.area_from_eic_code,
    e.area_to_eic_code,
    e.interconnector,
    e.is_hvdc,
    a.valid_from,
    a.valid_to,
    a.is_current
from {{ ref('dim_area') }} a
left join {{ ref('border_endpoints') }} e on e.border_area_eic_code = a.area_eic_code
where a.is_border_area or a.is_bidding_zone_border
