-- Elexon's BM Units and the EICs Elexon lists for them (its BM unit list), one row per pair and version. Most
-- units have none; a unit may have several.
select distinct
    elexon_bm_unit as resource_code,
    eic_code as resource_eic_code,
    valid_from,
    valid_to,
    is_current
from {{ ref('stg_bmrs__bmunits') }}
where elexon_bm_unit is not null and eic_code is not null
