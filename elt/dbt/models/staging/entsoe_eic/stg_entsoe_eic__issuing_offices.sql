select
    lio_code as issuing_office_code,
    name,
    nullif(country, '') as country_code,
    website as website_url,
    eic_site as eic_site_url,
    nullif(regexp_replace(email, '^mailto:', ''), '') as email,
    -- the sectors are published as icons
    coalesce(contains(operates_in, 'ee-icon-elec'), false) as operates_electricity,
    coalesce(contains(operates_in, 'ee-icon-gas'), false) as operates_gas,
    {{ scd2_validity() }},
    _dlt_load_id
from {{ dlt_source('entsoe_eic', 'entsoe_eic__issuing_offices') }}
