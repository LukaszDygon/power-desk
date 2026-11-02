# /// script
# requires-python = ">=3.13"
# dependencies = ["shapely>=2.0"]
# ///
"""Build the dashboard's bidding-zone map: one simplified GeoJSON feature per zone, keyed by EIC code.

Sources:
- entsoe-py v0.8.0 (MIT), `entsoe/geo/geojson`: the continental and Nordic zones, including the split
  DK, IT, NO and SE zones and DE_LU.
- Natural Earth 1:50m admin-0 map units v5.1.2 (public domain): zones entsoe-py does not publish, built
  from map units (GB = England + Scotland + Wales; SEM = Ireland + Northern Ireland).

    uv run dashboard/tools/build_bidding_zones.py
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ENTSOE_PY = "https://raw.githubusercontent.com/EnergieID/entsoe-py/v0.8.0/entsoe/geo/geojson/{zone}.geojson"
NATURAL_EARTH = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_50m_admin_0_map_units.geojson"
)
OUTPUT = Path(__file__).parents[1] / "frontend/static/geo/bidding_zones.geojson"
TOLERANCE_DEGREES = 0.02
MIN_PART_AREA = 0.005  # square degrees: drops islets too small to click

ENTSOE_PY_ZONES = {
    "AT": "10YAT-APG------L",
    "BE": "10YBE----------2",
    "BG": "10YCA-BULGARIA-R",
    "CH": "10YCH-SWISSGRIDZ",
    "CZ": "10YCZ-CEPS-----N",
    "DE_LU": "10Y1001A1001A82H",
    "DK_1": "10YDK-1--------W",
    "DK_2": "10YDK-2--------M",
    "EE": "10Y1001A1001A39I",
    "ES": "10YES-REE------0",
    "FI": "10YFI-1--------U",
    "FR": "10YFR-RTE------C",
    "GR": "10YGR-HTSO-----Y",
    "HR": "10YHR-HEP------M",
    "HU": "10YHU-MAVIR----U",
    "IT_CALA": "10Y1001C--00096J",
    "IT_CNOR": "10Y1001A1001A70O",
    "IT_CSUD": "10Y1001A1001A71M",
    "IT_NORD": "10Y1001A1001A73I",
    "IT_SARD": "10Y1001A1001A74G",
    "IT_SICI": "10Y1001A1001A75E",
    "IT_SUD": "10Y1001A1001A788",
    "LT": "10YLT-1001A0008Q",
    "LV": "10YLV-1001A00074",
    "NL": "10YNL----------L",
    "NO_1": "10YNO-1--------2",
    "NO_2": "10YNO-2--------T",
    "NO_3": "10YNO-3--------J",
    "NO_4": "10YNO-4--------9",
    "NO_5": "10Y1001A1001A48H",
    "PL": "10YPL-AREA-----S",
    "PT": "10YPT-REN------W",
    "RO": "10YRO-TEL------P",
    "RS": "10YCS-SERBIATSOV",
    "SE_1": "10Y1001A1001A44P",
    "SE_2": "10Y1001A1001A45N",
    "SE_3": "10Y1001A1001A46L",
    "SE_4": "10Y1001A1001A47J",
    "SI": "10YSI-ELES-----O",
    "SK": "10YSK-SEPS-----K",
}

# Natural Earth map units (GU_A3) per zone
NATURAL_EARTH_ZONES = {
    "10YGB----------A": ("ENG", "SCT", "WLS"),
    "10Y1001A1001A59C": ("IRL", "NIR"),
    "10YAL-KESH-----5": ("ALB",),
    "10YBA-JPCC-----D": ("BIS", "BHF"),
    "10YCS-CG-TSO---S": ("MNE",),
    "10YMK-MEPSO----8": ("MKD",),
    "10Y1001A1001A990": ("MDA",),
    "10Y1001C--00100H": ("KOS",),
    "10YCY-1001A0003J": ("CYP",),
    "10Y1001C--000182": ("UKR",),
    "10Y1001A1001A958": ("ISL",),
}


def fetch(url: str) -> dict:
    with urlopen(url) as response:
        return json.load(response)


def simplified(geometry):
    geometry = geometry.buffer(0).simplify(TOLERANCE_DEGREES, preserve_topology=True)
    parts = getattr(geometry, "geoms", [geometry])
    return unary_union([part for part in parts if part.area >= MIN_PART_AREA] or parts)


def rounded(coordinates):
    if isinstance(coordinates[0], (int, float)):
        return [round(value, 3) for value in coordinates]
    return [rounded(item) for item in coordinates]


def main() -> None:
    zones = {
        eic: unary_union([shape(f["geometry"]) for f in fetch(ENTSOE_PY.format(zone=zone))["features"]])
        for zone, eic in ENTSOE_PY_ZONES.items()
    }
    units = {f["properties"]["GU_A3"]: shape(f["geometry"]) for f in fetch(NATURAL_EARTH)["features"]}
    zones |= {eic: unary_union([units[unit] for unit in parts]) for eic, parts in NATURAL_EARTH_ZONES.items()}
    zones["10YCS-SERBIATSOV"] = zones["10YCS-SERBIATSOV"].difference(zones["10Y1001C--00100H"])

    features = []
    for eic, geometry in zones.items():
        geometry = mapping(simplified(geometry))
        features.append(
            {
                "type": "Feature",
                "properties": {"area_eic_code": eic},
                "geometry": {"type": geometry["type"], "coordinates": rounded(geometry["coordinates"])},
            }
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"{len(features)} zones -> {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
