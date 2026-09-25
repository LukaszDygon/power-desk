-- ODS View: Cleaned & Natural-Key Typed Actual National Demand Outturn
CREATE OR REPLACE VIEW ods_demand_actual AS
WITH raw AS (
    SELECT
        COALESCE(
            TRY_CAST(start_time AS TIMESTAMPTZ) AT TIME ZONE 'UTC',
            (TRY_CAST(settlement_date AS DATE) + INTERVAL ((TRY_CAST(settlement_period AS INT) - 1) * 30) MINUTE) 
                AT TIME ZONE 'Europe/London' AT TIME ZONE 'UTC'
        ) AS timestamp_utc,
        TRY_CAST(settlement_date AS DATE) AS settlement_date,
        TRY_CAST(settlement_period AS INTEGER) AS settlement_period,
        TRY_CAST(demand AS DOUBLE) AS national_demand_mw,
        TRY_CAST(publish_time AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS publish_time_utc
    FROM raw_indo
    WHERE settlement_date IS NOT NULL
)
SELECT * FROM raw;
