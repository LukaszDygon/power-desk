{#
  GB settlement day helpers (Elexon BSC conventions), for sources keyed on UK settlement
  periods. A settlement day runs midnight to midnight Europe/London, so it has 46 (spring),
  48 or 50 (autumn) half-hour periods. Period N starts (N - 1) * 30 minutes of elapsed time
  after local midnight.
#}

{# Local midnight of a settlement date, as TIMESTAMPTZ. #}
{% macro london_midnight(date_expr) -%}
    timezone('Europe/London', cast(cast({{ date_expr }} as date) as timestamp))
{%- endmacro %}

{# Start of a settlement period as naive UTC TIMESTAMP. #}
{% macro settlement_period_to_utc(date_expr, period_expr) -%}
    cast(({{ london_midnight(date_expr) }} + to_minutes(cast((cast({{ period_expr }} as integer) - 1) * 30 as bigint))) at time zone 'UTC' as timestamp)
{%- endmacro %}

{# Number of settlement periods in a settlement date. #}
{% macro settlement_periods_in_day(date_expr) -%}
    cast((epoch({{ london_midnight('cast(' ~ date_expr ~ ' as date) + 1') }}) - epoch({{ london_midnight(date_expr) }})) / 1800 as integer)
{%- endmacro %}

{# Settlement date / period containing a TIMESTAMPTZ instant. #}
{% macro utc_to_settlement_date(ts_expr) -%}
    cast(timezone('Europe/London', {{ ts_expr }}) as date)
{%- endmacro %}

{% macro utc_to_settlement_period(ts_expr) -%}
    cast(floor((epoch({{ ts_expr }}) - epoch({{ london_midnight(utc_to_settlement_date(ts_expr)) }})) / 1800) as integer) + 1
{%- endmacro %}
