{#
  Staging of an ECMWF open-data table (`ecmwf__<dataset>`): each field of the runs pending loads wrote
  (current versions), one row per forecast interval between consecutive published steps (UTC). A run
  is rebuilt whole, so every step finds its neighbours.

  - An instantaneous field (`step_type` instant) is a point in time: its value at a step is the value at
    the start of the interval to the next step (so the last step has no row).
  - An accumulated field (accum, accumulated from the run's start) covers the interval from the previous
    step: the difference of the two (so step 0 has no row).
  Both describe the same interval [`timestamp_utc`, + `interval_minutes`), which the entity joins on.
  - `packing_uncertainty`: how far `interval_value` can be from the model's value. Each field is packed
    to steps of 2^E x 10^-D (WMO GRIB2, Y x 10^D = R + X x 2^E), so a value is within half a step; a
    difference of two fields, within the larger of their steps. Steps follow each field's range.
#}
{% macro stg_ecmwf_fields(table_name) -%}
with current_rows as (
    select * from {{ dlt_source('ecmwf', table_name) }}
    where _dlt_valid_to is null
),

touched as (
    select distinct data_date, data_time
    from current_rows
    where {{ dlt_incremental_filter('_dlt_load_id') }}
),

fields as (
    select
        strptime(cast(c.data_date as varchar) || lpad(cast(c.data_time as varchar), 4, '0'), '%Y%m%d%H%M')
            as publish_time_utc,
        -- `startStep-endStep` (accumulations) or the step (instantaneous fields), in hours
        cast(split_part(c.step_range, '-', -1) as integer) as step_hours,
        c.step_type,
        c.param_id,
        c.short_name,
        c.units as grib_units,
        c.latitude as grid_latitude,
        c.longitude as grid_longitude,
        c.value,
        pow(2, c.binary_scale_factor) * pow(10, -c.decimal_scale_factor) as field_packing_step,
        c._dlt_load_id
    from current_rows c
    semi join touched t using (data_date, data_time)
),

stepped as (
    select
        *,
        lag(step_hours) over steps as previous_step_hours,
        lag(value) over steps as previous_value,
        lag(field_packing_step) over steps as previous_packing_step,
        lead(step_hours) over steps as next_step_hours
    from fields
    window steps as (partition by publish_time_utc, param_id, grid_latitude, grid_longitude order by step_hours)
),

intervals as (
    select
        *,
        if(step_type = 'accum', previous_step_hours, step_hours) as start_step_hours,
        if(step_type = 'accum', step_hours, next_step_hours) as end_step_hours
    from stepped
)

select
    publish_time_utc + to_hours(start_step_hours) as timestamp_utc,
    (end_step_hours - start_step_hours) * 60 as interval_minutes,
    publish_time_utc,
    step_hours,
    param_id,
    short_name,
    grib_units,
    step_type,
    grid_latitude,
    grid_longitude,
    if(step_type = 'accum', value - previous_value, value) as interval_value,
    if(step_type = 'accum', greatest(field_packing_step, previous_packing_step), field_packing_step / 2)
        as packing_uncertainty,
    _dlt_load_id
from intervals
where start_step_hours is not null and end_step_hours is not null
{%- endmacro %}


{#
  The measures of an entity row from the staged fields of one (run, interval, grid point), in the units
  of `dims.metrics`, by parameter id (short names are not unique: IFS `tp` is 228 in m, AIFS `tp` is
  228228 in kg m-2). Conversions follow the ECMWF Parameter Database: K - 273.15 = °C; an accumulated
  J m-2 divided by the accumulation period in seconds = W m-2; precipitation m x 1000 = mm, and
  kg m-2 of water = mm. Wind speed combines the U and V components.
#}
{% macro ecmwf_measures() -%}
    max(interval_value) filter (where param_id = 167) - 273.15 as temperature_2m_c,
    max(interval_value) filter (where param_id = 165) as wind_u_10m_ms,
    max(interval_value) filter (where param_id = 166) as wind_v_10m_ms,
    sqrt(max(interval_value) filter (where param_id = 165) ^ 2 + max(interval_value) filter (where param_id = 166) ^ 2)
        as wind_speed_10m_ms,
    max(interval_value) filter (where param_id = 228246) as wind_u_100m_ms,
    max(interval_value) filter (where param_id = 228247) as wind_v_100m_ms,
    sqrt(max(interval_value) filter (where param_id = 228246) ^ 2 + max(interval_value) filter (where param_id = 228247) ^ 2)
        as wind_speed_100m_ms,
    max(interval_value) filter (where param_id = 169) / (any_value(interval_minutes) * 60) as solar_radiation_wm2,
    max(interval_value) filter (where param_id = 164) as cloud_cover_fraction,
    coalesce(
        max(interval_value) filter (where param_id = 228) * 1000,
        max(interval_value) filter (where param_id = 228228)
    ) as precipitation_mm
{%- endmacro %}

{# The (parameter id, units) pairs `ecmwf_measures` converts; any other pair fails staging's tests. #}
{% macro ecmwf_known_units() -%}
    ((167, 'K'), (165, 'm s**-1'), (166, 'm s**-1'), (228246, 'm s**-1'), (228247, 'm s**-1'),
     (169, 'J m**-2'), (164, '(0 - 1)'), (228, 'm'), (228228, 'kg m**-2'))
{%- endmacro %}
