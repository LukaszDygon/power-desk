select
    s.timestamp_utc,
    s.settlement_date,
    s.settlement_period,
    s.demand_mw as transmission_demand_mw,
    s.publish_time_utc,
    ds.source_dataset,
    ds.default_area_eic_code as area_eic_code,
    s._dlt_load_id
from {{ ref('stg_bmrs__itsdo') }} s
join {{ ref('source_datasets') }} ds on ds.source_dataset = 'ITSDO'
