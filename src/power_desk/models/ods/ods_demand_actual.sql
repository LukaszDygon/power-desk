-- ODS View: Cleaned & Natural-Key Typed Actual National Demand Outturn
CREATE OR REPLACE VIEW ods_demand_actual AS
WITH raw AS (
    SELECT
        COALESCE(
            TRY_CAST("startTime" AS TIMESTAMPTZ) AT TIME ZONE 'UTC',
            (TRY_CAST("settlementDate" AS DATE) + INTERVAL ((TRY_CAST("settlementPeriod" AS INT) - 1) * 30) MINUTE) 
                AT TIME ZONE 'Europe/London' AT TIME ZONE 'UTC'
        ) AS timestamp_utc,
        TRY_CAST("settlementDate" AS DATE) AS settlement_date,
        TRY_CAST("settlementPeriod" AS INTEGER) AS settlement_period,
        TRY_CAST("demand" AS DOUBLE) AS national_demand_mw,
        TRY_CAST("publishTime" AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS publish_time_utc
    FROM raw_indo
    WHERE "settlementDate" IS NOT NULL
)
SELECT * FROM raw;
