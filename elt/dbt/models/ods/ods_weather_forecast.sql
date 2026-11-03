{#-
  Weather forecasts per site: every run's forecast intervals at the site's nearest grid point. A model's
  fields of one (run, interval, grid point) become one row of measures (`ecmwf_measures`).
  Keyed by row, not the entities' (hour, area, dataset): an hour holds every run's rows for every site, and
  delete+insert joins on the key. Rows are never withdrawn (`dim_site` keeps every site ever selected).
-#}
{{ config(unique_key=['timestamp_utc', 'site_code', 'publish_time_utc', 'source_dataset']) }}

with fields as (
    select
        timestamp_utc,
        interval_minutes,
        publish_time_utc,
        grid_latitude,
        grid_longitude,
        'ECMWF_IFS_OPER' as source_dataset,
        {{ ecmwf_measures() }},
        max(_dlt_load_id) as _dlt_load_id
    from {{ pending_partitions(ref('stg_ecmwf__ifs_oper')) }}
    group by timestamp_utc, interval_minutes, publish_time_utc, grid_latitude, grid_longitude

    union all

    select
        timestamp_utc,
        interval_minutes,
        publish_time_utc,
        grid_latitude,
        grid_longitude,
        'ECMWF_AIFS_SINGLE' as source_dataset,
        {{ ecmwf_measures() }},
        max(_dlt_load_id) as _dlt_load_id
    from {{ pending_partitions(ref('stg_ecmwf__aifs_single')) }}
    group by timestamp_utc, interval_minutes, publish_time_utc, grid_latitude, grid_longitude
),

grid_points as (
    select distinct source_dataset, grid_latitude, grid_longitude from fields
),

-- each site's nearest published grid point (the ingest extracted the point ecCodes finds nearest);
-- a regular 0.25° grid puts it within half a cell
site_points as (
    select s.site_code, s.area_eic_code, s.technology_code, g.source_dataset, g.grid_latitude, g.grid_longitude
    from {{ ref('dim_site') }} s
    join grid_points g
        on abs(g.grid_latitude - s.latitude) <= 0.13
        and abs(g.grid_longitude - s.longitude) <= 0.13
    qualify row_number() over (
        partition by s.site_code, g.source_dataset
        order by (g.grid_latitude - s.latitude) ^ 2 + ((g.grid_longitude - s.longitude) * cos(radians(s.latitude))) ^ 2
    ) = 1
)

select
    f.timestamp_utc,
    f.interval_minutes,
    p.area_eic_code,
    p.site_code,
    p.technology_code,
    f.temperature_2m_c,
    f.wind_u_10m_ms,
    f.wind_v_10m_ms,
    f.wind_speed_10m_ms,
    f.wind_u_100m_ms,
    f.wind_v_100m_ms,
    f.wind_speed_100m_ms,
    f.solar_radiation_wm2,
    f.cloud_cover_fraction,
    f.precipitation_mm,
    f.source_dataset,
    '*' as source_code,
    f.publish_time_utc,
    f._dlt_load_id
from fields f
join site_points p using (source_dataset, grid_latitude, grid_longitude)
