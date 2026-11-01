{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_energy_price'),
    series=['area_eic_code', 'time_horizon', 'classification_sequence', 'currency', 'source_dataset', 'source_code'],
    means=['price_per_mwh'],
    sums=['volume_mwh'],
) }}
