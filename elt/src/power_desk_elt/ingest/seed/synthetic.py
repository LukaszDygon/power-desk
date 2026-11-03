"""Synthetic Elexon BMRS, PVLive and NESO payloads for a seed week, shaped like the API records.

Deterministic (fixed random seed): FUELINST every 5 minutes per fuel type, INDO / ITSDO / NDF / MID
per settlement period, WINDFOR hourly, PVLive per half hour (half-hour ending); NESO net transfer
capacity restrictions per interconnector, the day-ahead submission and an evening intraday one per day;
REMIT messages for the units of the recorded BM unit list (`elt/seed/bmrs/bmunits.json`), covering a
revision that shortens an event, an outage profile, a message listing two units, a dismissed event, a
republished revision, an open-ended event, an unlisted asset and other market information.
ECMWF open-data step files (`ecmwf_step_file`): GRIB2 fields on a 0.25° grid over Great Britain and
Ireland, with their JSON-lines index, accumulated fields growing from the run's start.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from functools import cache
import json
import math
import random
from typing import Any
from zoneinfo import ZoneInfo

import eccodes
import numpy as np

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


REMIT_FIELDS = {
    "dataset": "REMIT",
    "messageType": "UnavailabilitiesOfElectricityFacilities",
    "biddingZone": "10YGB----------A",
}


def remit_message(message_id: int, mrid: str, revision: int, published: datetime, **fields: Any) -> dict[str, Any]:
    """One REMIT message as `/remit?messageId=` returns it: null fields are left out, as Elexon does."""
    message = {
        "id": message_id,
        **REMIT_FIELDS,
        "mrid": mrid,
        "revisionNumber": revision,
        "publishTime": iso(published),
        "createdTime": iso(published - timedelta(minutes=2)),
        **fields,
    }
    return {key: value for key, value in message.items() if value is not None}


def unit_outage(
    unit: str, eic: str | None, fuel: str | None, normal: float, available: float, start: datetime, end: datetime | None
) -> dict[str, Any]:
    return {
        "messageHeading": "Planned Unavailability of Generation Unit",
        "eventType": "Production unavailability",
        "unavailabilityType": "Planned",
        "participantId": "SEED",
        "registrationCode": "48X000000000SEED",
        "assetId": unit,
        "assetType": "Production",
        "affectedUnit": unit.removeprefix("T_"),
        "affectedUnitEIC": eic,
        "affectedArea": "N",
        "fuelType": fuel,
        "normalCapacity": normal,
        "availableCapacity": available,
        "unavailableCapacity": normal - available,
        "eventStatus": "Active",
        "eventStartTime": iso(start),
        "eventEndTime": iso(end) if end else None,
        "cause": "Planned Outage",
    }


def remit_records(start_date: str) -> list[dict[str, Any]]:
    """REMIT messages published in the seed week, by message id."""
    day = datetime.fromisoformat(start_date).replace(tzinfo=UTC)

    def at(days: int, hours: float = 0.0) -> datetime:
        return day + timedelta(days=days, hours=hours)

    def mrid(number: int, sender: str = "NGET") -> str:
        return f"48X000000000SEED-{sender}-RMT-{number:08d}"

    didcot = unit_outage("T_DIDCB5", "48W000000DIDCB5C", "Fossil Gas", 770, 0, at(2, 6), at(4, 18))
    drax = {
        **unit_outage("T_DRAXX-1", "48W00000DRAXX-1E", "Biomass", 665, 400, at(1, 14), at(2, 2)),
        "unavailabilityType": "Unplanned",
        "messageHeading": "Unplanned Unavailability of Generation Unit",
        "cause": "Mill Failure",
        "outageProfile": [
            {"startTime": iso(at(1, 14)), "endTime": iso(at(1, 20)), "capacity": 400.0},
            {"startTime": iso(at(1, 20)), "endTime": iso(at(2, 2)), "capacity": 500.0},
        ],
    }
    walney = unit_outage("T_WLNYO-4", "48W00000WLNYO-4-", "Wind Offshore", 330, 165, at(3, 8), at(3, 16))
    cairn = unit_outage("2__PSTAT001", "48W00000CAIRW-2E", "Wind Onshore", 42, 0, at(3, 8), at(3, 16))
    heysham = unit_outage("T_HEYM27", "48W000000HEYM27Y", "Nuclear", 660, 0, at(5, 0), at(6, 0))
    pembroke = unit_outage("T_PEMB-11", "48W00000PEMB-11T", "Fossil Gas", 475, 250, at(4, 7), at(4, 11))
    baglan = {**unit_outage("T_BAGE-1", "48W000000BAGE-1L", "Fossil Gas", 500, 300, at(2, 12), None),
              "durationUncertainty": "Unknown"}  # fmt: skip
    lion = unit_outage("T_LionB-1", None, "Other", 50, 0, at(1, 0), at(1, 6))
    moyle = {
        **unit_outage("I_IEG-MOYL1", None, None, 500, 250, at(5, 18), at(5, 22)),
        "eventType": "Transmission unavailability",
        "assetType": "Transmission",
        "biddingZone": "10YGB----------B",
        "affectedArea": None,
    }
    notice = {
        "messageType": "OtherMarketInformation",
        "messageHeading": "Interconnector Testing Market Notice",
        "participantId": "SEED",
        "registrationCode": "48X000000000SEED",
        "assetId": "NO_ASSET",
        "biddingZone": None,
        "eventStatus": "Active",
        "eventStartTime": iso(at(6, 3)),
        "eventEndTime": iso(at(6, 7)),
        "cause": "A short test is to be undertaken.",
    }
    didcot_shortened = {**didcot, "eventEndTime": iso(at(3, 20))}
    heysham_dismissed = {**heysham, "eventStatus": "Dismissed"}
    return [
        remit_message(101, mrid(1), 1, at(0, 9), **didcot),
        remit_message(102, mrid(2), 1, at(1, 14.5), **drax),
        remit_message(103, mrid(3, "ELXP"), 1, at(1, 0.5), **lion),
        remit_message(104, mrid(4), 1, at(2, 12.5), **baglan),
        remit_message(105, mrid(5), 1, at(2, 18), **walney),  # one message, two units
        remit_message(106, mrid(5), 1, at(2, 18), **cairn),
        remit_message(107, mrid(1), 2, at(3, 10), **didcot_shortened),
        remit_message(108, mrid(6), 1, at(3, 12), **heysham),
        remit_message(109, mrid(7), 3, at(3, 15), **pembroke),  # a revision Elexon republishes
        remit_message(110, mrid(7), 3, at(4, 9), **pembroke),
        remit_message(111, mrid(8), 1, at(4, 12), **moyle),
        remit_message(112, mrid(6), 2, at(5, 9), **heysham_dismissed),
        remit_message(113, mrid(9, "ELXP"), 1, at(5, 10), **notice),
    ]


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
    records["REMIT"] = remit_records(start_date)
    return dict(records)


# --- ECMWF open data ---------------------------------------------------------------------------------

GRID = {"north": 61.0, "south": 49.0, "west": -11.0, "east": 3.0, "step": 0.25}
ECMWF_FIELDS = {  # shortName -> accumulated
    "100u": False,
    "100v": False,
    "10u": False,
    "10v": False,
    "2t": False,
    "tcc": False,
    "ssrd": True,
    "tp": True,
}


def _grid() -> tuple[np.ndarray, np.ndarray]:
    step = GRID["step"]
    lats = np.arange(GRID["north"], GRID["south"] - step / 2, -step)
    lons = np.arange(GRID["west"], GRID["east"] + step / 2, step)
    lat, lon = np.meshgrid(lats, lons, indexing="ij")
    return lat, lon


def _field_values(short_name: str, run: datetime, step: int) -> np.ndarray:
    """Smooth, deterministic values over the grid; accumulations are totals since the run started."""
    lat, lon = _grid()
    valid = run + timedelta(hours=step)
    phase = valid.timestamp() / 3600.0 / 24.0 * 2 * math.pi
    if short_name == "2t":
        return 278.0 + 4.0 * np.sin(phase) - 0.3 * (lat - 55.0)
    if short_name in ("100u", "10u"):
        return (1.3 if short_name == "100u" else 1.0) * (6.0 + 3.0 * np.cos(phase + lon / 10.0))
    if short_name in ("100v", "10v"):
        return (1.3 if short_name == "100v" else 1.0) * (2.0 * np.sin(phase + lat / 10.0))
    if short_name == "tcc":
        return 0.5 + 0.4 * np.sin(phase + (lat + lon) / 5.0)
    if short_name == "ssrd":  # J m-2: up to 500 W m-2 around noon UTC, none at night
        hours = (run + timedelta(hours=h) for h in range(step))
        daylight = sum(max(0.0, math.sin((h.hour - 6) / 12.0 * math.pi)) for h in hours)
        return daylight * 500.0 * 3600.0 * (1.0 - (lat - 49.0) / 40.0)
    return 0.0002 * step * (1.0 + (lon + 11.0) / 14.0)  # tp, m


def _grib_message(short_name: str, accumulated: bool, run: datetime, step: int) -> bytes:
    handle = eccodes.codes_grib_new_from_samples("GRIB2")
    try:
        lat, _ = _grid()
        for key, value in (
            ("gridType", "regular_ll"),
            ("Ni", lat.shape[1]),
            ("Nj", lat.shape[0]),
            ("latitudeOfFirstGridPointInDegrees", GRID["north"]),
            ("longitudeOfFirstGridPointInDegrees", GRID["west"]),
            ("latitudeOfLastGridPointInDegrees", GRID["south"]),
            ("longitudeOfLastGridPointInDegrees", GRID["east"]),
            ("iDirectionIncrementInDegrees", GRID["step"]),
            ("jDirectionIncrementInDegrees", GRID["step"]),
            ("dataDate", int(f"{run:%Y%m%d}")),
            ("dataTime", run.hour * 100),
        ):
            eccodes.codes_set(handle, key, value)
        if accumulated:
            eccodes.codes_set(handle, "productDefinitionTemplateNumber", 8)
        eccodes.codes_set(handle, "shortName", short_name)
        if accumulated:
            eccodes.codes_set(handle, "stepType", "accum")
            eccodes.codes_set(handle, "stepRange", f"0-{step}" if step else "0")
        else:
            eccodes.codes_set(handle, "stepRange", str(step))
        eccodes.codes_set_values(handle, np.ravel(_field_values(short_name, run, step)))
        return eccodes.codes_get_message(handle)
    finally:
        eccodes.codes_release(handle)


@cache
def ecmwf_step_file(stream: str, run: datetime, step: int) -> tuple[str, bytes]:
    """A step file's JSON-lines index and GRIB2 content, as the open-data portal lays them out."""
    content, index = b"", []
    for short_name, accumulated in ECMWF_FIELDS.items():
        message = _grib_message(short_name, accumulated, run, step)
        index.append(
            {
                "domain": "g",
                "date": f"{run:%Y%m%d}",
                "time": f"{run:%H}00",
                "expver": "0001",
                "class": "od",
                "type": "fc",
                "stream": stream,
                "step": str(step),
                "levtype": "sfc",
                "param": short_name,
                "_offset": len(content),
                "_length": len(message),
            }
        )
        content += message
    return "".join(json.dumps(entry) + "\n" for entry in index), content
