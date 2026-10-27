select
    eic_code,
    -- published type column; the Reference Manual (4.1) says not to derive information from the code itself
    type as eic_type,
    -- the exception it defines: the first two characters identify the issuing office (5.3)
    left(eic_code, 2) as issuing_office_code,
    nullif(trim(eic_display_name), '') as display_name,
    nullif(trim(eic_long_name), '') as long_name,
    nullif(trim(eic_parent), '') as parent_eic_code,
    nullif(trim(eic_responsible_party), '') as responsible_party_eic_code,
    eic_status as status,
    nullif(trim(market_participant_iso_country_code), '') as country_code,
    nullif(trim(market_participant_postal_code), '') as postal_code,
    nullif(trim(market_participant_vat_code), '') as vat_code,
    list_filter(list_transform(string_split(coalesce(eic_type_function_list, ''), ','), f -> trim(f)), f -> f <> '') as roles,
    {{ eic_check_character('eic_code') }} = substr(eic_code, 16, 1) as has_valid_check_character,
    {{ scd2_validity() }},
    _dlt_load_id
from {{ source('entsoe_eic', 'raw_eic_codes') }}
