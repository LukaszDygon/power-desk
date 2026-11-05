{#
  Staging of a NESO net transfer capacity table (`neso__<interconnector>_ntc`): the current versions
  (scd2) under each (operational period, auction) pending loads wrote; where NESO appended a
  resubmission as a further row, the latest upload. The hourly period's length is the dataset's
  (`dim_source_dataset.native_interval_minutes`), joined by the entity.
#}
{% macro stg_neso_ntc(table_name) -%}
with current_rows as (
    select * from {{ dlt_source('neso', table_name) }}
    where _dlt_valid_to is null
),

touched as (
    select distinct operational_period_start_date_and_time_gmt, auction_type
    from current_rows
    where {{ dlt_incremental_filter('_dlt_load_id') }}
)

select
    cast(c.operational_period_start_date_and_time_gmt at time zone 'UTC' as timestamp) as timestamp_utc,
    c.auction_type,
    cast(c.flow_in_mw_to_gb as double) as to_gb_mw,
    c.reason_for_restriction_to_gb as to_gb_restriction_reason,
    cast(c.flow_in_mw_from_gb as double) as from_gb_mw,
    c.reason_for_restriction_from_gb as from_gb_restriction_reason,
    cast(c.data_upload_time_gmt at time zone 'UTC' as timestamp) as publish_time_utc,
    c._dlt_load_id
from current_rows c
semi join touched t using (operational_period_start_date_and_time_gmt, auction_type)
qualify row_number() over (
    partition by c.operational_period_start_date_and_time_gmt, c.auction_type
    order by c.data_upload_time_gmt desc, c._dlt_id
) = 1
{%- endmacro %}
