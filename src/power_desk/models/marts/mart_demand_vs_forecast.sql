-- Mart View: Actual Demand vs Day-Ahead Forecast Alignment
CREATE OR REPLACE VIEW mart_demand_vs_forecast AS
SELECT
    COALESCE(a.timestamp_utc, f.timestamp_utc) AS timestamp_utc,
    COALESCE(a.settlement_date, f.settlement_date) AS settlement_date,
    COALESCE(a.settlement_period, f.settlement_period) AS settlement_period,
    a.national_demand_mw AS actual_demand_mw,
    f.forecast_demand_mw AS forecast_demand_mw,
    ROUND(a.national_demand_mw - f.forecast_demand_mw, 1) AS delta_mw,
    ROUND(
        CASE 
            WHEN a.national_demand_mw IS NOT NULL AND a.national_demand_mw > 0 
            THEN (ABS(a.national_demand_mw - f.forecast_demand_mw) / a.national_demand_mw) * 100.0 
            ELSE NULL 
        END, 
        2
    ) AS absolute_error_pct
FROM ods_demand_actual a
FULL OUTER JOIN ods_demand_forecast f
    ON a.settlement_date = f.settlement_date 
   AND a.settlement_period = f.settlement_period;
