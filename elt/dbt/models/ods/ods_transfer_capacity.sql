{{ config(unique_key=['timestamp_utc', 'out_area_eic_code', 'in_area_eic_code', 'source_dataset']) }}

{#- NESO dataset -> staging model; the dataset's border (map_border) gives the interconnector and its areas -#}
{%- set neso_models = {
    'NESO_IFA': 'stg_neso__ifa_ntc',
    'NESO_IFA2': 'stg_neso__ifa2_ntc',
    'NESO_ELECLINK': 'stg_neso__eleclink_ntc',
    'NESO_NEMOLINK': 'stg_neso__nemolink_ntc',
    'NESO_NSL': 'stg_neso__nsl_ntc',
    'NESO_VIKING': 'stg_neso__viking_ntc',
} %}

with neso_restrictions as (
    {%- for source_dataset, model in neso_models.items() %}
    select '{{ source_dataset }}' as source_dataset, * from {{ pending_partitions(ref(model)) }}
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
),

neso_interconnectors as (
    select m.source_dataset, m.border_area_eic_code, e.area_from_eic_code as gb_eic_code, e.area_to_eic_code as connected_eic_code
    from {{ ref('map_border') }} m
    join {{ ref('source_datasets') }} ds using (source_dataset)
    join {{ ref('border_endpoints') }} e
        on e.border_area_eic_code = m.border_area_eic_code and e.area_from_eic_code = ds.default_area_eic_code
),

-- each NESO row restricts both directions: imports (to GB) and exports (from GB)
neso_directions as (
    select
        r.*,
        i.border_area_eic_code,
        d.to_gb,
        case when d.to_gb then i.connected_eic_code else i.gb_eic_code end as out_area_eic_code,
        case when d.to_gb then i.gb_eic_code else i.connected_eic_code end as in_area_eic_code
    from neso_restrictions r
    join neso_interconnectors i using (source_dataset)
    cross join (values (true), (false)) as d(to_gb)
)

select
    timestamp_utc,
    interval_minutes,
    out_area_eic_code,
    in_area_eic_code,
    border_area_eic_code,
    case when auction_type = 'Day Ahead' then 'day_ahead' when auction_type like 'Intraday%' then 'intraday' end
        as time_horizon,
    case when to_gb then to_gb_mw else from_gb_mw end as transfer_capacity_mw,
    case when to_gb then to_gb_restriction_reason else from_gb_restriction_reason end as restriction_reason,
    source_dataset,
    auction_type as source_code,
    publish_time_utc,
    _dlt_load_id
from neso_directions

union all

select
    timestamp_utc,
    interval_minutes,
    out_area_eic_code,
    in_area_eic_code,
    cast(null as varchar) as border_area_eic_code,
    replace(lower(contract_type), '-', '_') as time_horizon,
    transfer_capacity_mw,
    cast(null as varchar) as restriction_reason,
    'ENTSOE_11.1.A' as source_dataset,
    contract_type as source_code,
    publish_time_utc,
    _dlt_load_id
from {{ pending_partitions(ref('stg_entsoe__forecasted_transfer_capacities'), ['out_area_eic_code', 'in_area_eic_code']) }}
