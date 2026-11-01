{{ config(unique_key=['timestamp_utc', '_series_key']) }}

{{ hourly_series(
    ref('ods_transfer_capacity'),
    series=['out_area_eic_code', 'in_area_eic_code', 'border_area_eic_code', 'time_horizon', 'source_dataset', 'source_code'],
    means=['transfer_capacity_mw'],
    latest=['restriction_reason'],
) }}
