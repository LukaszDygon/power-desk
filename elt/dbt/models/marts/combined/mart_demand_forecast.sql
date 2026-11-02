{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_demand_forecast'),
    series=['area_eic_code', 'time_horizon', 'source_dataset'],
    means=['demand_mw'],
) }}
