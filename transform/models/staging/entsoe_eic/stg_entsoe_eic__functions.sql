select
    trim(eic_function) as role,
    trim(eic_type) as eic_type,
    nullif(nullif(trim(definition), ''), 'Missing definition.') as role_definition,
    trim(valid_in_market) as market,
    {{ scd2_validity() }},
    _dlt_load_id
from {{ source('entsoe_eic', 'raw_eic_functions') }}
