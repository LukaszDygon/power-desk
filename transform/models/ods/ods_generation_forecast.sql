with windfor as (
    select
        s.timestamp_utc,
        ds.native_interval_minutes as interval_minutes,
        ds.default_area_eic_code as area_eic_code,
        '*' as source_code,
        'current' as forecast_horizon,
        s.generation_mw,
        s.publish_time_utc,
        ds.source_dataset,
        ds.source_dataset as code_list,
        s._dlt_load_id
    from {{ ref('stg_bmrs__windfor') }} s
    join {{ ref('source_datasets') }} ds on ds.source_dataset = 'WINDFOR'
),

-- one row per published horizon; an area changing its market time unit publishes the overlap at both
-- resolutions: keep the finest
entsoe as (
    {% for horizon in ['day_ahead', 'intraday', 'current'] %}
    select
        timestamp_utc,
        interval_minutes,
        area_eic_code,
        psr_type as source_code,
        '{{ horizon }}' as forecast_horizon,
        {{ horizon }}_forecast_mw as generation_mw,
        publish_time_utc,
        'ENTSOE_14.1.D' as source_dataset,
        'ENTSOE_PSR' as code_list,
        _dlt_load_id
    from {{ ref('stg_entsoe__wind_solar_forecast') }}
    where {{ horizon }}_forecast_mw is not null
    {{ keep_finest_resolution(['area_eic_code', 'production_type']) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

unioned as (
    select * from windfor
    union all
    select * from entsoe
)

select
    u.timestamp_utc,
    u.interval_minutes,
    u.area_eic_code,
    mt.technology_code,
    u.forecast_horizon,
    u.generation_mw,
    u.source_dataset,
    u.source_code,
    u.publish_time_utc,
    u._dlt_load_id
from unioned u
left join {{ ref('map_technology') }} mt on mt.source_dataset = u.code_list and mt.source_code = u.source_code
