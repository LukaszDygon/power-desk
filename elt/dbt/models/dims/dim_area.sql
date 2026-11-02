select
    eic_code as area_eic_code,
    display_name,
    long_name,
    country_code,
    roles,
    {% for role in ['Bidding Zone', 'Control Area', 'Scheduling Area', 'Market Balance Area', 'LFC Area',
                    'LFC Block', 'Member State', 'Synchronous Area', 'Capacity Calculation Region',
                    'Border Area', 'Bidding Zone Border', 'Market Area', 'Metering Grid Area'] %}
    list_contains(roles, '{{ role }}') as is_{{ role | lower | replace(' ', '_') }},
    {% endfor %}
    valid_from,
    valid_to,
    is_current
from {{ ref('dim_eic_code') }}
where eic_type = 'Y'
