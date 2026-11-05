select
    load_id,
    schema_name,
    status,
    inserted_at,
    to_timestamp(cast(load_id as double)) as loaded_at,
    schema_version_hash
from {{ dlt_source('dlt', '_dlt_loads') }}
