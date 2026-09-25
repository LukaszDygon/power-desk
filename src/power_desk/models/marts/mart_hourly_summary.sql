-- Mart View: Consolidated Hourly Power Desk Rollup
CREATE OR REPLACE VIEW mart_hourly_summary AS
SELECT
    DATE_TRUNC('hour', g.timestamp_utc) AS hour_utc,
    DATE(g.timestamp_utc) AS date_utc,
    ROUND(AVG(d.actual_demand_mw), 1) AS avg_demand_mw,
    ROUND(AVG(d.forecast_demand_mw), 1) AS avg_forecast_demand_mw,
    ROUND(AVG(g.total_generation_mw), 1) AS avg_generation_mw,
    ROUND(AVG(g.wind_mw), 1) AS avg_wind_mw,
    ROUND(AVG(g.solar_mw), 1) AS avg_solar_mw,
    ROUND(AVG(g.nuclear_mw), 1) AS avg_nuclear_mw,
    ROUND(AVG(g.ccgt_gas_mw), 1) AS avg_gas_mw,
    ROUND(AVG(g.clean_share_pct), 1) AS avg_clean_share_pct,
    ROUND(MAX(d.actual_demand_mw), 1) AS peak_demand_mw,
    ROUND(MIN(d.actual_demand_mw), 1) AS min_demand_mw
FROM mart_generation_mix g
LEFT JOIN mart_demand_vs_forecast d
    ON g.timestamp_utc = d.timestamp_utc
GROUP BY DATE_TRUNC('hour', g.timestamp_utc), DATE(g.timestamp_utc);
