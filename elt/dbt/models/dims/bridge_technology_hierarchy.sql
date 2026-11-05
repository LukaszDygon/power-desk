with recursive closure(technology_code, ancestor_technology_code, depth) as (
    select technology_code, technology_code, 0 from {{ ref('dim_technology') }}
    union all
    select c.technology_code, t.parent_technology_code, c.depth + 1
    from closure c
    join {{ ref('dim_technology') }} t on t.technology_code = c.ancestor_technology_code
    where t.parent_technology_code is not null and c.depth < 10
)
select technology_code, ancestor_technology_code, depth from closure
