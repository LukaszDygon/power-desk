{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_demand_actual'),
    series=['area_eic_code', 'source_dataset'],
    means=['demand_mw'],
) }}
