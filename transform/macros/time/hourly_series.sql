{#
  An entity (`relation`, rows at their published interval) on an hourly spine: one row per series and
  hour holding data. `series` lists the columns identifying a series; `_series_key` hashes them (a DuckDB
  upgrade changing `hash` needs a full refresh).

  - Precedence: where rows of a series overlap in an hour (a period republished at another resolution),
    the most recently published row prevails, slot by slot (5 minutes, the finest published interval);
    ties go to the latest load, then the finest resolution. Rows of one resolution lie on its grid, so an
    hour overlaps when it mixes resolutions or its rows add up to more minutes than they span.
  - `coverage`: the fraction of the hour (0.0-1.0) holding data from the series' source.
  - `means`: rates and levels (MW, prices, capacities), the time-weighted mean over the covered minutes
    (times `coverage`, the mean over the hour with missing minutes as zero).
  - `sums`: volumes over the published interval (MWh), pro-rated by its minutes in the hour (divided by
    `coverage`, an estimate for the whole hour).
  - `latest`: attributes of the most recently published row.
  - Calendar periods (a day or month, `interval_minutes` >= 1440) start at the publisher's local
    midnight, so in UTC a day lasts 23 or 25 hours at clock changes: such a period ends where the
    series' next period of its resolution starts, when that is within an hour of its nominal end.

  Incremental builds recompute the (series, hour) pairs that rows of pending loads overlap, and for a
  calendar period the hour either side, which a neighbouring period's end may move into.
#}
{% macro hourly_series(relation, series, means=[], sums=[], latest=[]) -%}
{#- refs rendered unconditionally so dbt registers the dependencies at parse time -#}
{%- set _ = [ref('dlt_loads'), ref('dlt_load_audit')] -%}
{%- set slot_minutes = 5 -%}
{%- set hours_of = "unnest(generate_series(time_bucket(interval 1 hour, timestamp_utc), _end_utc - interval 1 microsecond, interval 1 hour))" -%}
{%- set calendar = "interval_minutes >= 1440" -%}
{%- set keyed -%}
    select
        *,
        hash({{ series | join(', ') }}) as _series_key,
        timestamp_utc + to_minutes(interval_minutes) as _nominal_end_utc
    from {{ relation }}
{%- endset -%}
with
{%- if is_incremental() %}
touched as (
    select distinct
        _series_key,
        unnest(generate_series(
            time_bucket(interval 1 hour, timestamp_utc) - if({{ calendar }}, interval 1 hour, interval 0 hour),
            _nominal_end_utc + if({{ calendar }}, interval 1 hour, interval 0 hour) - interval 1 microsecond,
            interval 1 hour
        )) as hour_utc
    from ({{ keyed }} where {{ dlt_incremental_filter('_dlt_load_id') }})
),
{%- endif %}

-- rows overlapping the hours to build (incremental: those pending loads touch, give or take a calendar
-- period's moved end; pruned by time first)
keyed as not materialized (
    {{ keyed }}
    {%- if is_incremental() %}
    where timestamp_utc < (select max(hour_utc) from touched) + interval 2 hour
      and _nominal_end_utc + interval 1 hour > (select min(hour_utc) from touched)
    {%- endif %}
),

source as not materialized (
    select * exclude (_nominal_end_utc), _nominal_end_utc as _end_utc, time_bucket(interval 1 hour, timestamp_utc) as _first_hour
    from keyed
    where not {{ calendar }}
    union all by name
    select
        * exclude (_nominal_end_utc, _next_start_utc),
        if(
            abs(datediff('minute', _nominal_end_utc, _next_start_utc)) <= 60, _next_start_utc, _nominal_end_utc
        ) as _end_utc,
        time_bucket(interval 1 hour, timestamp_utc) as _first_hour
    from (
        select *, lead(timestamp_utc) over (
            partition by _series_key, interval_minutes >= 28 * 1440 order by timestamp_utc
        ) as _next_start_utc
        from keyed
        where {{ calendar }}
    )
),

-- each row in every hour it overlaps (rows within one hour need no expansion)
row_hours as not materialized (
    select *, _first_hour as hour_utc from source where _end_utc <= _first_hour + interval 1 hour
    union all
    select *, {{ hours_of }} as hour_utc from source where _end_utc > _first_hour + interval 1 hour
),

spans as not materialized (
    select
        *,
        greatest(timestamp_utc, hour_utc) as _from_utc,
        datediff('minute', greatest(timestamp_utc, hour_utc), least(_end_utc, hour_utc + interval 1 hour)) as _minutes
    from row_hours
    {%- if is_incremental() %}
    where (_series_key, hour_utc) in (select _series_key, hour_utc from touched)
    {%- endif %}
),

-- the series' columns, once per series (aggregating them per hour would cost more than the measures)
series_columns as (
    select _series_key, {% for column in series %}any_value({{ column }}) as {{ column }}{{ ', ' if not loop.last }}{% endfor %}
    from spans
    group by _series_key
),

{%- set aggregates %}
    hour_utc as timestamp_utc,
    {#- sums of integers in thousandths: exact, so builds agree whatever the summation order -#}
    {%- for measure in means %}
    round(
        sum(cast(round({{ measure }} * 1000) as bigint) * _minutes)
            / nullif(sum(_minutes) filter (where {{ measure }} is not null), 0) / 1000,
        3
    ) as {{ measure }},
    {%- endfor %}
    {%- for measure in sums %}
    sum(cast(round({{ measure }} * 1000 * _minutes / interval_minutes) as bigint)) / 1000 as {{ measure }},
    {%- endfor %}
    {%- for column in latest %}
    arg_max({{ column }}, publish_time_utc) as {{ column }},
    {%- endfor %}
    round(sum(_minutes) / 60.0, 4) as coverage,
    max(publish_time_utc) as publish_time_utc,
    _series_key,
    max(_dlt_load_id) as _last_dlt_load_id
{%- endset %}

-- one pass assuming no overlap; an hour overlaps where it mixes resolutions or its rows add up to more
-- minutes than they span
aggregated as (
    select
        {{ aggregates }},
        min(interval_minutes) <> max(interval_minutes)
            or sum(_minutes) > datediff('minute', min(_from_utc), max(_from_utc + to_minutes(_minutes))) as _overlapping
    from spans
    group by _series_key, hour_utc
),

-- overlapping hours: each slot held by the most recently published row
prevailing as (
    select * exclude (_slot_utc, _minutes), {{ slot_minutes }} as _minutes
    from (
        select
            s.*,
            unnest(generate_series(
                s._from_utc, s._from_utc + to_minutes(s._minutes - {{ slot_minutes }}), interval {{ slot_minutes }} minute
            )) as _slot_utc
        from spans s
        semi join (select _series_key, timestamp_utc as hour_utc from aggregated where _overlapping) o
            using (_series_key, hour_utc)
    )
    qualify row_number() over (
        partition by _series_key, _slot_utc
        order by publish_time_utc desc nulls last, _dlt_load_id desc, interval_minutes
    ) = 1
)

select a.timestamp_utc, {% for column in series %}c.{{ column }}, {% endfor %}a.* exclude (timestamp_utc, _overlapping)
from (
    select * from aggregated where not _overlapping
    union all by name
    select {{ aggregates }}
    from prevailing
    group by _series_key, hour_utc
) a
join series_columns c using (_series_key)
{%- endmacro %}
