select
    c.eic_code,
    c.eic_type,
    t.name as eic_type_name,
    c.issuing_office_code,
    o.name as issuing_office_name,
    c.display_name,
    c.long_name,
    c.parent_eic_code,
    c.responsible_party_eic_code,
    c.country_code,
    c.roles,
    c.has_valid_check_character,
    c.valid_from,
    c.valid_to,
    c.is_current
from {{ ref('stg_entsoe_eic__codes') }} c
left join {{ ref('eic_code_types') }} t on t.eic_type = c.eic_type
left join {{ ref('stg_entsoe_eic__issuing_offices') }} o
    on o.issuing_office_code = c.issuing_office_code and o.is_current
