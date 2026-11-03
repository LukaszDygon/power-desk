-- Each current resource with itself and every containing resource, following published EIC parents (BM Units
-- have none published: depth 0 only).
with recursive closure(resource_code, ancestor_resource_code, depth, path) as (
    select resource_code, resource_code, 0, [resource_code]
    from {{ ref('dim_resource') }}
    where is_current
    union all
    select c.resource_code, p.parent_eic_code, c.depth + 1, list_append(c.path, p.parent_eic_code)
    from closure c
    join {{ ref('dim_eic_code') }} p on p.eic_code = c.ancestor_resource_code and p.is_current
    where p.parent_eic_code is not null and not list_contains(c.path, p.parent_eic_code) and c.depth < 10
)
select distinct resource_code, ancestor_resource_code, depth
from closure
