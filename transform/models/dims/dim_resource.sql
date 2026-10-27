select
    eic_code as resource_eic_code, display_name, long_name, country_code, roles,
    parent_eic_code as parent_resource_eic_code,
    responsible_party_eic_code,
    valid_from, valid_to, is_current
from {{ ref('dim_eic_code') }}
where eic_type = 'W'
