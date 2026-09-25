-- ODS View: Deduplicated Day-Ahead Demand Forecasts
CREATE OR REPLACE VIEW ods_demand_forecast AS
WITH ranked AS (
    SELECT
        (TRY_CAST(settlement_date AS DATE) + INTERVAL ((TRY_CAST(settlement_period AS INT) - 1) * 30) MINUTE) 
            AT TIME ZONE 'Europe/London' AT TIME ZONE 'UTC' AS timestamp_utc,
        TRY_CAST(settlement_date AS DATE) AS settlement_date,
        TRY_CAST(settlement_period AS INTEGER) AS settlement_period,
        TRY_CAST(national_demand AS DOUBLE) AS forecast_demand_mw,
        TRY_CAST(transmission_system_demand AS DOUBLE) AS forecast_ts_demand_mw,
        TRY_CAST(publish_time AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS publish_time_utc,
        ROW_NUMBER() OVER (
            PARTITION BY settlement_date, settlement_period 
            ORDER BY publish_time DESC
        ) AS rn
    FROM raw_demand_forecast
    WHERE settlement_date IS NOT NULL
      AND (boundary = 'N' OR boundary IS NULL)
)
SELECT 
    timestamp_utc,
    settlement_date,
    settlement_period,
    forecast_demand_mw,
    forecast_ts_demand_mw,
    publish_time_utc
FROM ranked
WHERE rn = 1;
