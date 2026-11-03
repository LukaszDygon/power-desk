select
    trim(cast(ref_id as varchar)) as site_code,
    nullif(trim(site_name), '') as site_name,
    nullif(trim(operator_or_applicantx), '') as operator_name,
    nullif(trim(technology_type), '') as technology_type,
    try_cast(installed_capacity_m_welecx as double) as installed_capacity_mw,
    nullif(trim(development_status), '') as development_status,
    nullif(trim(development_status_shortx), '') as development_status_short,
    -- published with stray spaces (e.g. "England ")
    nullif(trim(country), '') as country,
    nullif(trim(region), '') as region,
    try_cast(x_coordinate as double) as x_coordinate,
    try_cast(y_coordinate as double) as y_coordinate,
    cast(try_strptime(nullif(trim(operational), ''), '%d/%m/%Y') as date) as operational_date,
    {{ scd2_validity() }},
    _dlt_load_id
from {{ dlt_source('desnz_repd', 'desnz_repd__repd') }}
