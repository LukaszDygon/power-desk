-- Mart View: Half-Hourly Power Generation Mix by Fuel
CREATE OR REPLACE VIEW mart_generation_mix AS
WITH pivoted AS (
    SELECT
        timestamp_utc,
        settlement_date,
        settlement_period,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type = 'WIND' THEN generation_mw END), 0), 1) AS wind_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type = 'SOLAR' THEN generation_mw END), 0), 1) AS solar_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type = 'NUCLEAR' THEN generation_mw END), 0), 1) AS nuclear_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type = 'CCGT' THEN generation_mw END), 0), 1) AS ccgt_gas_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type = 'BIOMASS' THEN generation_mw END), 0), 1) AS biomass_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type IN ('NPSHYD', 'PS') THEN generation_mw END), 0), 1) AS hydro_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type = 'COAL' THEN generation_mw END), 0), 1) AS coal_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type LIKE 'INT%' THEN generation_mw END), 0), 1) AS imports_mw,
        ROUND(COALESCE(SUM(CASE WHEN fuel_type IN ('OCGT', 'OIL', 'OTHER') THEN generation_mw END), 0), 1) AS other_fossil_mw,
        ROUND(COALESCE(SUM(generation_mw), 0), 1) AS total_generation_mw
    FROM ods_generation_actual
    GROUP BY timestamp_utc, settlement_date, settlement_period
)
SELECT
    *,
    ROUND(
        CASE 
            WHEN total_generation_mw > 0 
            THEN ((wind_mw + solar_mw + nuclear_mw + biomass_mw + hydro_mw) / total_generation_mw) * 100.0 
            ELSE 0 
        END, 
        1
    ) AS clean_share_pct
FROM pivoted;
