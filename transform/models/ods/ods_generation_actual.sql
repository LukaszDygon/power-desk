with fuelinst as (
    select
        timestamp_utc, settlement_date, settlement_period, fuel_type, generation_mw, publish_time_utc,
        'FUELINST' as source_dataset,
        _dlt_load_id
    from {{ ref('stg_bmrs__fuelinst') }}
),

-- half-hourly rows spread over the six 5-minute intervals of their period
pvlive as (
    select
        s.timestamp_utc + to_minutes(cast(t.tick * 5 as bigint)) as timestamp_utc,
        s.settlement_date,
        s.settlement_period,
        'SOLAR' as fuel_type,
        s.generation_mw,
        s.publish_time_utc,
        'PVLIVE' as source_dataset,
        s._dlt_load_id
    from {{ ref('stg_pvlive__solar') }} s
    cross join range(6) t(tick)
),

unioned as (
    select * from fuelinst
    union all
    select * from pvlive
)

select
    u.*,
    ds.default_area_eic_code as area_eic_code,
    mt.technology_code,
    mb.border_area_eic_code
from unioned u
left join {{ ref('source_datasets') }} ds on ds.source_dataset = u.source_dataset
left join {{ ref('map_technology') }} mt on mt.source_dataset = u.source_dataset and mt.source_code = u.fuel_type
left join {{ ref('map_border') }} mb on mb.source_dataset = u.source_dataset and mb.source_code = u.fuel_type
