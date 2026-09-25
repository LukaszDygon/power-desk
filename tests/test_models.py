"""Tests for DuckDB SQL transformations (ODS & Marts views) and UTC mapping."""

from __future__ import annotations

from datetime import datetime
import pytest
from power_desk.db import get_db


def test_settlement_to_utc_resolution():
    """Verify DuckDB accurately resolves UK settlement date + period to UTC."""
    db = get_db()
    # Period 1 in winter (GMT = UTC+0)
    res_winter = db.execute_query("""
        SELECT 
            ('2024-01-15'::DATE + INTERVAL ((1 - 1) * 30) MINUTE) 
                AT TIME ZONE 'Europe/London' AT TIME ZONE 'UTC' as ts_utc
    """)
    ts_w = res_winter["rows"][0][0]
    assert "2024-01-15T00:00:00" in ts_w

    # Period 1 in summer (BST = UTC+1) -> 00:00 BST should resolve to 23:00 UTC previous day
    res_summer = db.execute_query("""
        SELECT 
            ('2024-07-01'::DATE + INTERVAL ((1 - 1) * 30) MINUTE) 
                AT TIME ZONE 'Europe/London' AT TIME ZONE 'UTC' as ts_utc
    """)
    ts_s = res_summer["rows"][0][0]
    assert "2024-06-30T23:00:00" in ts_s


def test_ods_views_available():
    db = get_db()
    for view in ["ods_generation_actual", "ods_demand_actual", "ods_demand_forecast", "ods_generation_forecast"]:
        res = db.execute_query(f"SELECT COUNT(*) FROM {view}")
        assert res["row_count"] == 1
        assert res["rows"][0][0] > 0


def test_mart_generation_mix_clean_share():
    db = get_db()
    res = db.execute_query("""
        SELECT 
            wind_mw, solar_mw, nuclear_mw, ccgt_gas_mw, total_generation_mw, clean_share_pct
        FROM mart_generation_mix
        LIMIT 5
    """)
    assert res["row_count"] == 5
    for row in res["rows"]:
        total = row[4]
        clean_share = row[5]
        assert total > 0
        assert 0.0 <= clean_share <= 100.0


def test_mart_demand_vs_forecast_deltas():
    db = get_db()
    res = db.execute_query("""
        SELECT actual_demand_mw, forecast_demand_mw, delta_mw
        FROM mart_demand_vs_forecast
        WHERE actual_demand_mw IS NOT NULL AND forecast_demand_mw IS NOT NULL
        LIMIT 5
    """)
    assert res["row_count"] == 5
    for row in res["rows"]:
        actual, fc, delta = row[0], row[1], row[2]
        assert round(actual - fc, 1) == round(delta, 1)
