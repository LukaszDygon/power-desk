select
    timestamp_utc,
    interval_minutes,
    area_eic_code,
    time_horizon,
    classification_sequence,
    price_per_mwh,
    currency,
    volume_mwh,
    source_dataset,
    source_code,
    _dlt_load_id
from {{ ref('ods_energy_price') }}
