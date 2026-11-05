-- the loads `dlt_pending_load_ids_sql` (macros/dlt/loads.sql) defines as pending for some tracked model
-- depends_on: {{ ref('dlt_load_audit') }}
select l.load_id, l.schema_name, l.loaded_at
from {{ ref('dlt_loads') }} l
where l.load_id in ({{ dlt_pending_load_ids_sql() }})
