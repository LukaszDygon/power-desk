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
from {{ dlt_source('entsoe_eic', 'entsoe_eic__issuing_offices') }}
