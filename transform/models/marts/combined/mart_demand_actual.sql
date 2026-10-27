select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    demand_mw,
    source_dataset,
    _dlt_load_id
from {{ ref('ods_demand_actual') }}
