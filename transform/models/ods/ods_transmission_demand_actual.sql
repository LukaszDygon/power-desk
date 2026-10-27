select
    s.timestamp_utc,
    ds.native_interval_minutes as interval_minutes,
    ds.default_area_eic_code as area_eic_code,
    s.demand_mw,
    ds.source_dataset,
    s.settlement_date,
    s.settlement_period,
    s.publish_time_utc,
    s._dlt_load_id
from {{ ref('stg_bmrs__itsdo') }} s
join {{ ref('source_datasets') }} ds on ds.source_dataset = 'ITSDO'
