with recursive links as (
    select area_eic_code as child_area_eic_code, parent_eic_code as parent_area_eic_code, 'eic_parent' as relation
    from (select a.area_eic_code, c.parent_eic_code
          from {{ ref('dim_area') }} a
          join {{ ref('dim_eic_code') }} c on c.eic_code = a.area_eic_code and c.valid_from = a.valid_from
          where a.is_current and c.parent_eic_code is not null)
    union
    select child_area_eic_code, parent_area_eic_code, relation
    from {{ ref('area_hierarchy') }}
),

closure(area_eic_code, ancestor_area_eic_code, depth, path) as (
    select area_eic_code, area_eic_code, 0, [area_eic_code]
    from {{ ref('dim_area') }}
    where is_current
    union all
    select c.area_eic_code, l.parent_area_eic_code, c.depth + 1, list_append(c.path, l.parent_area_eic_code)
    from closure c
    join links l on l.child_area_eic_code = c.ancestor_area_eic_code
    where not list_contains(c.path, l.parent_area_eic_code) and c.depth < 10
),

registered as (
    select area_eic_code, ancestor_area_eic_code, min(depth) as depth
    from closure
    group by area_eic_code, ancestor_area_eic_code
),

-- a nonconforming code (seed `nonconforming_eic_codes`) rolls up through the registered area it stands for, one
-- level further. Kept out of the recursion: a third `links` branch on dim_area made DuckDB 1.5.4 crash
-- intermittently in the recursive CTE's join filter (ADR 0005).
nonconforming as (
    select a.area_eic_code, r.ancestor_area_eic_code, r.depth + 1 as depth
    from {{ ref('dim_area') }} a
    join registered r on r.area_eic_code = a.registered_area_eic_code
    where a.is_current and a.area_eic_code <> a.registered_area_eic_code
)

select area_eic_code, ancestor_area_eic_code, min(depth) as depth
from (select * from registered union all select * from nonconforming)
group by area_eic_code, ancestor_area_eic_code
