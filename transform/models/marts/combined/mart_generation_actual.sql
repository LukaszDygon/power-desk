select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    technology_code,
    border_area_eic_code,
    generation_mw,
    consumption_mw,
    source_dataset,
    source_code,
    _dlt_load_id
from {{ ref('ods_generation_actual') }}
