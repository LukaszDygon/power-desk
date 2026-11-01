{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_generation_actual'),
    series=['area_eic_code', 'technology_code', 'border_area_eic_code', 'source_dataset', 'source_code'],
    means=['generation_mw', 'consumption_mw'],
) }}
