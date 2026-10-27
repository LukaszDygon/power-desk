select
    eic_code as party_eic_code, display_name, long_name, country_code, roles,
    valid_from, valid_to, is_current
from {{ ref('dim_eic_code') }}
where eic_type = 'X'
