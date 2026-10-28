with fuelinst as (
    select
        timestamp_utc, 5 as interval_minutes, settlement_date, settlement_period,
        fuel_type as source_code, generation_mw, cast(null as double) as consumption_mw, publish_time_utc,
        'FUELINST' as source_dataset, 'FUELINST' as code_list, cast(null as varchar) as area_eic_code,
        _dlt_load_id
    from {{ ref('stg_bmrs__fuelinst') }}
),

-- half-hourly rows spread over the six 5-minute intervals of their period
pvlive as (
    select
        s.timestamp_utc + to_minutes(cast(t.tick * 5 as bigint)) as timestamp_utc,
        5 as interval_minutes,
        s.settlement_date,
        s.settlement_period,
        'SOLAR' as source_code,
        s.generation_mw,
        cast(null as double) as consumption_mw,
        s.publish_time_utc,
        'PVLIVE' as source_dataset,
        'PVLIVE' as code_list,
        cast(null as varchar) as area_eic_code,
        s._dlt_load_id
    from {{ ref('stg_pvlive__solar') }} s
    cross join range(6) t(tick)
),

entsoe as (
    select
        timestamp_utc, interval_minutes, cast(null as date) as settlement_date, cast(null as integer) as settlement_period,
        psr_type as source_code, generation_mw, consumption_mw, publish_time_utc,
        'ENTSOE_16.1.B_C' as source_dataset, 'ENTSOE_PSR' as code_list, area_eic_code,
        _dlt_load_id
    from {{ ref('stg_entsoe__generation_per_type') }}
    -- an area changing its market time unit publishes the overlap at both resolutions: keep the finest
    {{ keep_finest_resolution(['area_eic_code', 'production_type']) }}
),

unioned as (
    select * from fuelinst
    union all
    select * from pvlive
    union all
    select * from entsoe
)

select
    u.timestamp_utc,
    u.interval_minutes,
    coalesce(u.area_eic_code, ds.default_area_eic_code) as area_eic_code,
    mt.technology_code,
    mb.border_area_eic_code,
    u.generation_mw,
    u.consumption_mw,
    u.source_dataset,
    u.source_code,
    u.settlement_date,
    u.settlement_period,
    u.publish_time_utc,
    u._dlt_load_id
from unioned u
left join {{ ref('source_datasets') }} ds on ds.source_dataset = u.source_dataset
left join {{ ref('map_technology') }} mt on mt.source_dataset = u.code_list and mt.source_code = u.source_code
left join {{ ref('map_border') }} mb on mb.source_dataset = u.source_dataset and mb.source_code = u.source_code
