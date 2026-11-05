{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_weather_forecast'),
    series=['area_eic_code', 'site_code', 'technology_code', 'source_dataset', 'source_code'],
) }}
