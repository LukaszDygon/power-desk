{#- ENTSO-E forecast column -> its label in map_time_horizon (the export publishes one column per horizon) -#}
{%- set entsoe_horizons = {
    'Day-ahead': 'day_ahead_forecast_mw',
    'Intraday': 'intraday_forecast_mw',
    'Current': 'current_forecast_mw',
} %}

with unioned as (
    select
        timestamp_utc, cast(null as integer) as interval_minutes, cast(null as varchar) as area_eic_code,
        '*' as source_code, '*' as horizon_code, generation_mw, publish_time_utc,
        'WINDFOR' as source_dataset, 'WINDFOR' as code_list, _dlt_load_id
    from {{ pending_partitions(ref('stg_bmrs__windfor')) }}

    -- one row per published horizon
    {%- for label, column in entsoe_horizons.items() %}
    union all
    select
        timestamp_utc, interval_minutes, area_eic_code,
        psr_type as source_code, '{{ label }}' as horizon_code, {{ column }} as generation_mw, publish_time_utc,
        'ENTSOE_14.1.D' as source_dataset, 'ENTSOE_PSR' as code_list, _dlt_load_id
    from {{ pending_partitions(ref('stg_entsoe__wind_solar_forecast'), ['area_eic_code']) }}
    where {{ column }} is not null
    {%- endfor %}
)

-- the interval and area each source publishes, else the dataset's (dim_source_dataset)
select
    u.timestamp_utc,
    coalesce(u.interval_minutes, ds.native_interval_minutes) as interval_minutes,
    coalesce(u.area_eic_code, ds.default_area_eic_code) as area_eic_code,
    mt.technology_code,
    h.time_horizon,
    u.generation_mw,
    u.source_dataset,
    u.source_code,
    u.publish_time_utc,
    u._dlt_load_id
from unioned u
left join {{ ref('dim_source_dataset') }} ds on ds.source_dataset = u.source_dataset
left join {{ ref('map_technology') }} mt on mt.source_dataset = u.code_list and mt.source_code = u.source_code
left join {{ ref('map_time_horizon') }} h on h.source_dataset = u.source_dataset and h.source_code = u.horizon_code
