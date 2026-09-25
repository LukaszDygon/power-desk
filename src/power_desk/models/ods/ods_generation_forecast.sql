-- ODS View: Day-Ahead Wind Generation Forecast
CREATE OR REPLACE VIEW ods_generation_forecast AS
WITH ranked AS (
    SELECT
        TRY_CAST("startTime" AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS timestamp_utc,
        TRY_CAST("generation" AS DOUBLE) AS forecast_wind_mw,
        TRY_CAST("publishTime" AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS publish_time_utc,
        ROW_NUMBER() OVER (
            PARTITION BY "startTime" 
            ORDER BY "publishTime" DESC
        ) AS rn
    FROM raw_windfor
    WHERE "startTime" IS NOT NULL
)
SELECT
    timestamp_utc,
    forecast_wind_mw,
    publish_time_utc
FROM ranked
WHERE rn = 1;
