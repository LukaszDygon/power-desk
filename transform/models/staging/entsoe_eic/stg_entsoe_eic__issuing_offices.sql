select
    lio_code as issuing_office_code,
    name,
    nullif(country, '') as country_code,
    website as website_url,
    eic_site as eic_site_url,
    email,
    electricity as operates_electricity,
    gas as operates_gas,
    {{ scd2_validity() }},
    _dlt_load_id
from {{ source('entsoe_eic', 'raw_eic_issuing_offices') }}
