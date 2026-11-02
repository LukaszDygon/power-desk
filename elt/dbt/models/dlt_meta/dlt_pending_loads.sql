{% set tracked = dlt_tracked_models() %}

select l.load_id, l.schema_name, l.loaded_at
from {{ ref('dlt_loads') }} l
where l.status = 0
  and (
    select count(distinct a.model_name)
    from {{ ref('dlt_load_audit') }} a
    where a.load_id = l.load_id
      {% if tracked %}and a.model_name in ({% for m in tracked %}'{{ m }}'{% if not loop.last %}, {% endif %}{% endfor %}){% endif %}
  ) < {{ tracked | length }}
