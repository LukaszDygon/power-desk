{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_generation_forecast'),
    series=['area_eic_code', 'technology_code', 'time_horizon', 'source_dataset', 'source_code'],
    means=['generation_mw'],
) }}
