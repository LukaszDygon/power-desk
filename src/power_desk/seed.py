"""Seed generator for Power Desk.

Generates realistic 7-day UK power system data (half-hourly settlement periods 1-48)
strictly matching the raw Elexon BMRS API schema for raw_fuelinst, raw_indo,
raw_demand_forecast, and raw_windfor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from pathlib import Path
import random

import duckdb

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed"


def generate_seed_data(
    start_date: str = "2024-03-01",
    num_days: int = 7,
    output_dir: Path | str | None = None,
) -> dict[str, int]:
    """Generate realistic Elexon BMRS raw parquet datasets."""
    out_path = Path(output_dir or SEED_DIR)
    out_path.mkdir(parents=True, exist_ok=True)

    start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    random.seed(42)

    fuelinst_records = []
    indo_records = []
    demand_fc_records = []
    windfor_records = []

    fuels = ["CCGT", "NUCLEAR", "WIND", "SOLAR", "BIOMASS", "NPSHYD", "PS", "COAL", "INTFR", "INTNED"]

    for d_idx in range(num_days):
        curr_d = start_d + timedelta(days=d_idx)
        date_str = curr_d.strftime("%Y-%m-%d")

        # Base daily wind trend with autocorrelation
        daily_wind_base = 5000 + 7000 * math.sin(d_idx * 0.8)

        for period in range(1, 49):
            # Half-hour timestamp in UTC
            period_start = datetime(curr_d.year, curr_d.month, curr_d.day) + timedelta(minutes=(period - 1) * 30)
            iso_start = period_start.strftime("%Y-%m-%dT%H:%M:%SZ")
            iso_publish = (period_start + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

            # Time of day factors (0.0 to 24.0 hours)
            hour = (period - 1) * 0.5

            # Diurnal demand curve: dip at night (4am), double peak (9am and 6pm)
            demand_curve = (
                22000
                + 12000 * math.sin((hour - 4) / 24.0 * math.pi) ** 2
                + 4000 * math.exp(-((hour - 18) ** 2) / 8.0)
            )
            actual_demand = round(demand_curve + random.gauss(0, 400))
            forecast_demand = round(demand_curve + random.gauss(0, 750))

            # Fuel generation:
            # Solar: peaks between 10am and 3pm
            solar_factor = max(0.0, math.sin((hour - 6) / 14.0 * math.pi)) if 6 <= hour <= 20 else 0.0
            solar_gen = round(solar_factor * 6500 + random.uniform(0, 200)) if solar_factor > 0 else 0

            # Wind: stochastic breeze
            wind_gen = round(max(800, daily_wind_base + 2500 * math.sin(hour / 4.0) + random.gauss(0, 300)))
            wind_fc = round(max(800, wind_gen + random.gauss(0, 600)))

            # Nuclear: steady baseload
            nuclear_gen = round(4200 + random.gauss(0, 50))

            # Biomass: steady thermal
            biomass_gen = round(2100 + random.gauss(0, 40))

            # Hydro / Pumped storage
            hydro_gen = round(350 + (400 if 17 <= hour <= 20 else 50))

            # Interconnectors
            intfr_gen = round(1500 + 300 * math.sin(hour))
            intned_gen = round(800 + 200 * math.cos(hour))

            # CCGT Gas: balancing generation
            clean_baseload = solar_gen + wind_gen + nuclear_gen + biomass_gen + hydro_gen + intfr_gen + intned_gen
            gas_needed = max(1500, actual_demand - clean_baseload)
            gas_gen = round(gas_needed + random.gauss(0, 150))

            # 1. FUELINST records
            fuel_map = {
                "CCGT": gas_gen,
                "NUCLEAR": nuclear_gen,
                "WIND": wind_gen,
                "SOLAR": solar_gen,
                "BIOMASS": biomass_gen,
                "NPSHYD": hydro_gen,
                "PS": 50,
                "COAL": 0,
                "INTFR": intfr_gen,
                "INTNED": intned_gen,
            }
            for fuel, gen in fuel_map.items():
                fuelinst_records.append({
                    "dataset": "FUELINST",
                    "publishTime": iso_publish,
                    "startTime": iso_start,
                    "settlementDate": date_str,
                    "settlementPeriod": period,
                    "fuelType": fuel,
                    "generation": gen,
                })

            # 2. INDO demand record
            indo_records.append({
                "dataset": "INDO",
                "publishTime": iso_publish,
                "startTime": iso_start,
                "settlementDate": date_str,
                "settlementPeriod": period,
                "demand": actual_demand,
            })

            # 3. Demand Forecast record
            demand_fc_records.append({
                "startTime": iso_start,
                "settlementDate": date_str,
                "settlementPeriod": period,
                "boundary": "N",
                "publishTime": (period_start - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "transmissionSystemDemand": actual_demand + 1200,
                "nationalDemand": forecast_demand,
            })

            # 4. Wind Forecast record
            windfor_records.append({
                "dataset": "WINDFOR",
                "publishTime": (period_start - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "startTime": iso_start,
                "generation": wind_fc,
            })

    # Save to parquet using DuckDB
    import json
    import tempfile
    con = duckdb.connect()

    with tempfile.TemporaryDirectory() as tmpdir:
        for tbl_name, recs in [
            ("raw_fuelinst", fuelinst_records),
            ("raw_indo", indo_records),
            ("raw_demand_forecast", demand_fc_records),
            ("raw_windfor", windfor_records),
        ]:
            tmp_json = Path(tmpdir) / f"{tbl_name}.json"
            tmp_json.write_text(json.dumps(recs), encoding="utf-8")
            con.execute(f"CREATE TABLE {tbl_name} AS SELECT * FROM read_json_auto('{tmp_json.as_posix()}')")
            con.execute(f"COPY {tbl_name} TO '{(out_path / f'{tbl_name}.parquet').as_posix()}' (FORMAT PARQUET)")

    con.close()

    return {
        "raw_fuelinst": len(fuelinst_records),
        "raw_indo": len(indo_records),
        "raw_demand_forecast": len(demand_fc_records),
        "raw_windfor": len(windfor_records),
    }


if __name__ == "__main__":
    res = generate_seed_data()
    print("Seed parquet files generated successfully:", res)
