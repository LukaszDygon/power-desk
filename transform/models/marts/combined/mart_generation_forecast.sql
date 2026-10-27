select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    technology_code,
    forecast_horizon,
    generation_mw,
    source_dataset,
    source_code,
    _dlt_load_id
from {{ ref('ods_generation_forecast') }}
