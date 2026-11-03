-- ENTSO-E's central registry, plus the codes publishers use that do not conform to the EIC scheme
-- (seed `nonconforming_eic_codes`). Each nonconforming code takes every version of the registered code it
-- stands for (`registered_eic_code`), and has no issuing office.
with registered as (
    select
        c.eic_code,
        c.eic_type,
        t.name as eic_type_name,
        c.issuing_office_code,
        o.name as issuing_office_name,
        c.display_name,
        c.long_name,
        c.parent_eic_code,
        c.responsible_party_eic_code,
        c.country_code,
        c.roles,
        c.has_valid_check_character,
        c.eic_code as registered_eic_code,
        c.valid_from,
        c.valid_to,
        c.is_current
    from {{ ref('stg_entsoe_eic__codes') }} c
    left join {{ ref('eic_code_types') }} t on t.eic_type = c.eic_type
    left join {{ ref('stg_entsoe_eic__issuing_offices') }} o
        on o.issuing_office_code = c.issuing_office_code and o.is_current
),

nonconforming as (
    select
        n.eic_code,
        n.eic_type,
        r.eic_type_name,
        cast(null as varchar) as issuing_office_code,
        cast(null as varchar) as issuing_office_name,
        r.display_name,
        r.long_name,
        r.parent_eic_code,
        r.responsible_party_eic_code,
        r.country_code,
        r.roles,
        {{ eic_check_character('n.eic_code') }} = substr(n.eic_code, 16, 1) as has_valid_check_character,
        r.eic_code as registered_eic_code,
        r.valid_from,
        r.valid_to,
        r.is_current
    from {{ ref('nonconforming_eic_codes') }} n
    join registered r on r.eic_code = n.registered_eic_code and r.eic_type = n.eic_type
)

select * from registered
union all
select * from nonconforming
