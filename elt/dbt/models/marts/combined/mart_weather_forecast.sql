{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_weather_forecast'),
    series=['area_eic_code', 'site_code', 'technology_code', 'source_dataset', 'source_code'],
    means=[
        'temperature_2m_c', 'wind_u_10m_ms', 'wind_v_10m_ms', 'wind_speed_10m_ms', 'wind_u_100m_ms',
        'wind_v_100m_ms', 'wind_speed_100m_ms', 'solar_radiation_wm2', 'cloud_cover_fraction',
    ],
    sums=['precipitation_mm'],
) }}
