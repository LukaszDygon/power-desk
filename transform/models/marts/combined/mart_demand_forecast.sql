select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    forecast_horizon,
    demand_mw,
    source_dataset,
    _dlt_load_id
from {{ ref('ods_demand_forecast') }}
