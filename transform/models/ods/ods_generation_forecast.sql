select
    s.timestamp_utc,
    s.generation_mw as forecast_wind_mw,
    s.publish_time_utc,
    ds.source_dataset,
    ds.default_area_eic_code as area_eic_code,
    mt.technology_code,
    s._dlt_load_id
from {{ ref('stg_bmrs__windfor') }} s
join {{ ref('source_datasets') }} ds on ds.source_dataset = 'WINDFOR'
left join {{ ref('map_technology') }} mt on mt.source_dataset = ds.source_dataset and mt.source_code = '*'
