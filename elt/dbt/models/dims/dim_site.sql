{{ config(materialized='table') }}

{#-
  The sites to read weather for (the `weather_site_*` vars): every REPD project with a published version
  that was an operational wind or solar project of at least the minimum capacity, with that version's
  attributes. The `ecmwf` source reads the selected ones (`is_selected`) by reference, so the rule and the
  coordinate conversion live only here. A table, so readers need no spatial extension.
-#}
with qualifying as (
    select *
    from {{ ref('stg_desnz_repd__repd') }}
    where development_status_short = '{{ var("weather_site_status") }}'
      and technology_type in ({% for t in var('weather_site_technologies') %}'{{ t }}'{{ ', ' if not loop.last }}{% endfor %})
      and installed_capacity_mw >= {{ var('weather_site_min_capacity_mw') }}
      and x_coordinate is not null
      and y_coordinate is not null
    qualify row_number() over (partition by site_code order by valid_from desc) = 1
),

located as (
    select
        *,
        -- REPD coordinates are British National Grid, Northern Ireland included
        ST_Transform(ST_Point(x_coordinate, y_coordinate), 'EPSG:27700', 'EPSG:4326', always_xy := true) as point
    from qualifying
)

select
    l.site_code,
    l.site_name,
    l.operator_name,
    mt.technology_code,
    l.installed_capacity_mw,
    ma.area_eic_code,
    ST_Y(l.point) as latitude,
    ST_X(l.point) as longitude,
    l.operational_date,
    l.is_current as is_selected
from located l
left join {{ ref('map_technology') }} mt on mt.source_dataset = 'REPD' and mt.source_code = l.technology_type
left join {{ ref('map_area') }} ma on ma.source_dataset = 'REPD' and ma.source_code = l.country
