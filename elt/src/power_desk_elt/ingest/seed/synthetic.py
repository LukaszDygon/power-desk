"""Synthetic Elexon BMRS, PVLive and NESO payloads for a seed week, shaped like the API records.

Deterministic (fixed random seed): FUELINST every 5 minutes per fuel type, INDO / ITSDO / NDF / MID
per settlement period, WINDFOR hourly, PVLive per half hour (half-hour ending); NESO net transfer
capacity restrictions per interconnector, the day-ahead submission and an evening intraday one per day.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
import math
import random
from typing import Any
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
Records = dict[str, list[dict[str, Any]]]


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def settlement_periods(day: date) -> list[tuple[int, datetime]]:
    """(period, UTC start) of every settlement period of a UK settlement day (46, 48 or 50)."""
    start = datetime(day.year, day.month, day.day, tzinfo=LONDON).astimezone(UTC)
    following = day + timedelta(days=1)
    end = datetime(following.year, following.month, following.day, tzinfo=LONDON).astimezone(UTC)
    return [
        (p, start + timedelta(minutes=30 * (p - 1))) for p in range(1, int((end - start).total_seconds() // 1800) + 1)
    ]


def demand_profile(hour: float) -> float:
    return 22000 + 12000 * math.sin((hour - 4) / 24.0 * math.pi) ** 2 + 4000 * math.exp(-((hour - 18) ** 2) / 8.0)


def fuel_mix(hour: float, wind_base: float, demand: int) -> tuple[dict[str, int], int, int]:
    """Generation per FUELINST fuel type, plus solar and wind; gas fills the gap to demand."""
    solar_factor = max(0.0, math.sin((hour - 6) / 14.0 * math.pi)) if 6 <= hour <= 20 else 0.0
    solar = round(solar_factor * 6500 + random.uniform(0, 200)) if solar_factor > 0 else 0
    wind = round(max(800, wind_base + 2500 * math.sin(hour / 4.0) + random.gauss(0, 300)))
    nuclear = round(4200 + random.gauss(0, 50))
    biomass = round(2100 + random.gauss(0, 40))
    hydro = round(350 + (400 if 17 <= hour <= 20 else 50))
    intfr = round(1500 + 300 * math.sin(hour))
    intned = round(800 + 200 * math.cos(hour))
    gas = round(max(1500, demand - (solar + wind + nuclear + biomass + hydro + intfr + intned)) + random.gauss(0, 150))
    fuels = {
        "CCGT": gas,
        "OCGT": 0,
        "OIL": 0,
        "COAL": 0,
        "NUCLEAR": nuclear,
        "WIND": wind,
        "PS": 50,
        "NPSHYD": hydro,
        "OTHER": 120,
        "BIOMASS": biomass,
        "INTFR": intfr,
        "INTNED": intned,
    }
    return fuels, solar, wind


def fuelinst(period_start: datetime, settlement: dict[str, Any], fuels: dict[str, int]) -> list[dict[str, Any]]:
    """Six 5-minute records per fuel type for one settlement period."""
    return [
        {
            "dataset": "FUELINST",
            "publishTime": iso(tick + timedelta(minutes=5)),
            "startTime": iso(tick),
            **settlement,
            "fuelType": fuel,
            "generation": max(0, generation + (round(random.gauss(0, 25)) if generation else 0)),
        }
        for tick in (period_start + timedelta(minutes=5 * i) for i in range(6))
        for fuel, generation in fuels.items()
    ]


def market_index(period_start: datetime, settlement: dict[str, Any], demand: int) -> list[dict[str, Any]]:
    """One record per data provider; N2EX publishes zero price and volume, as it does live."""
    priced = {"APXMIDP": (round(35 + (demand - 22000) / 250, 2), round(1500 + demand / 20, 3)), "N2EXMIDP": (0.0, 0.0)}
    return [
        {
            "dataset": "MID",
            "startTime": iso(period_start),
            "dataProvider": provider,
            **settlement,
            "price": price,
            "volume": volume,
        }
        for provider, (price, volume) in priced.items()
    ]


def period_records(day: date, period: int, period_start: datetime, wind_base: float) -> Records:
    hour = (period - 1) * 0.5
    settlement = {"settlementDate": day.isoformat(), "settlementPeriod": period}
    demand = demand_profile(hour)
    actual, forecast = round(demand + random.gauss(0, 400)), round(demand + random.gauss(0, 750))
    fuels, solar, wind = fuel_mix(hour, wind_base, actual)
    published = {"publishTime": iso(period_start + timedelta(minutes=30)), "startTime": iso(period_start), **settlement}
    records: Records = {
        "FUELINST": fuelinst(period_start, settlement, fuels),
        "INDO": [{"dataset": "INDO", **published, "demand": actual}],
        "ITSDO": [{"dataset": "ITSDO", **published, "demand": actual + 1200}],
        "NDF": [
            {
                "dataset": "NDF",
                "demand": forecast,
                "publishTime": iso(period_start - timedelta(hours=12)),
                "startTime": iso(period_start),
                **settlement,
                "boundary": "N",
            }
        ],
        "PVLIVE": [
            {"pes_id": 0, "datetime_gmt": iso(period_start + timedelta(minutes=30)), "generation_mw": float(solar)}
        ],
        "MID": market_index(period_start, settlement, actual),
    }
    if period_start.minute == 0:
        records["WINDFOR"] = [
            {
                "dataset": "WINDFOR",
                "publishTime": iso(period_start - timedelta(hours=12)),
                "startTime": iso(period_start),
                "generation": round(max(800, wind + random.gauss(0, 600))),
            }
        ]
    return records


# NESO datasets (raw table) -> interconnector capability in MW, both directions
NESO_CAPACITY_MW = {
    "neso__ifa_ntc": 2000,
    "neso__ifa2_ntc": 1014,
    "neso__eleclink_ntc": 1014,
    "neso__nemolink_ntc": 1032,
    "neso__nsl_ntc": 1400,
    "neso__viking_ntc": 1457,
}


def neso_restriction(auction: str, period_start: datetime, uploaded: datetime, capacity: int) -> dict[str, Any]:
    """One NESO row; exports from GB are restricted in the evening peak, more so intraday."""
    restricted = 17 <= period_start.hour <= 19
    from_gb = round(capacity * (0.3 if auction != "Day Ahead" else 0.6)) if restricted else capacity
    return {
        "Data Upload Time GMT": uploaded.strftime("%Y-%m-%dT%H:%M:%S"),
        "Auction Type": auction,
        "Operational Period Start Date and Time GMT": period_start.strftime("%Y-%m-%dT%H:%M:%S"),
        "Flow in MW To GB": capacity,
        "Reason For Restriction To GB": "No Restriction",
        "Flow in MW From GB": from_gb,
        "Reason For Restriction From GB": "Network Constraints" if restricted else "No Restriction",
    }


def neso_records(day: date) -> Records:
    """Uploaded on `day`: the next day's day-ahead hours (09:30) and its evening intraday hours (18:30)."""
    following = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)
    hours = [following + timedelta(hours=h) for h in range(24)]
    day_ahead, intraday = following - timedelta(hours=14, minutes=30), following - timedelta(hours=5, minutes=30)
    return {
        resource: [neso_restriction("Day Ahead", hour, day_ahead, capacity) for hour in hours]
        + [neso_restriction("Intraday 1", hour, intraday, capacity) for hour in hours if 17 <= hour.hour <= 20]
        for resource, capacity in NESO_CAPACITY_MW.items()
    }


def generate(start_date: str, num_days: int) -> Records:
    """Records per dataset code (`FUELINST`, ..., `PVLIVE`, NESO raw table) for `num_days` from `start_date`."""
    random.seed(42)
    records: Records = defaultdict(list)
    for day_index in range(num_days):
        day = date.fromisoformat(start_date) + timedelta(days=day_index)
        wind_base = 5000 + 7000 * math.sin(day_index * 0.8)
        for period, period_start in settlement_periods(day):
            for code, rows in period_records(day, period, period_start, wind_base).items():
                records[code] += rows
        for resource, rows in neso_records(day).items():
            records[resource] += rows
    return dict(records)
