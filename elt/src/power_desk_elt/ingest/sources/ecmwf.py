"""ECMWF open data: medium-range weather forecasts at the grid points nearest to GB wind and solar sites.

ECMWF publishes each forecast run on its open-data portal (https://www.ecmwf.int/en/forecasts/datasets/open-data)
as one GRIB2 file per forecast step, `<run>-<step>h-<stream>-<type>.grib2`, with a JSON-lines `.index` giving
each field's byte range. The portal keeps about the 12 most recent runs. A run reads only the surface
fields in `PARAMS`, one byte range each, and keeps the values at the grid points nearest to the
operational wind and solar sites of at least 50 MW in DESNZ's Renewable Energy Planning Database
(`desnz_repd`), as eccodes (ECMWF's GRIB library) finds them.

A row is one field's value at one grid point, with the field's GRIB keys as published (`dataDate`,
`dataTime`, `stepRange`, `shortName`, ...) and the grid point's `latitude` / `longitude`. Accumulated
fields (`ssrd`, `tp`) hold the total since the run started (`stepRange` `0-<step>`). Runs are a stream:
the cursor is the run date (`dataDate`), every key holds the run time, and each dataset's table keeps
the versions of its rows (`scd2`) merged on the natural key, so a run loaded again changes nothing. A run
is read once it is complete (its last step published); open-ended runs skip runs already loaded.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
import logging
import time
from typing import Any

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltResource
import duckdb
import eccodes

from power_desk_elt.ingest import http
from power_desk_elt.ingest.sources import desnz_repd
from power_desk_elt.ingest.spec import RunWindow, SourceSpec
from power_desk_elt.ingest.windows import DateRange, incremental_window

logger = logging.getLogger(__name__)

BASE_URL = "https://data.ecmwf.int/forecasts"
SCD2: TMergeDispositionDict = {"disposition": "merge", "strategy": "scd2"}
PARAMS = frozenset({"100u", "100v", "10u", "10v", "2t", "ssrd", "tcc", "tp"})  # surface fields read
GRIB_KEYS = (
    "dataDate",
    "dataTime",
    "stepRange",
    "stepType",
    "shortName",
    "paramId",
    "units",
    "typeOfLevel",
    "level",
    "binaryScaleFactor",  # with decimalScaleFactor, the field's packing precision (2^E x 10^-D)
    "decimalScaleFactor",
)
NATURAL_KEY = ["dataDate", "dataTime", "stepRange", "shortName", "latitude", "longitude"]  # the merge key
CURSOR = "dataDate"
PAGE_ROWS = 50_000
FETCH_WORKERS = 8  # concurrent step files; the portal allows 500-2000 connections
RUNS_REMEMBERED = 32  # loaded runs kept in resource state (the portal keeps ~12)
REVISIT_DAYS = 1  # a run completing after midnight is still read

# Sites: operational wind and solar projects of at least 50 MW in the REPD
SITE_TECHNOLOGIES = frozenset({"Wind Onshore", "Wind Offshore", "Solar Photovoltaics"})
SITE_STATUS = "Operational"
SITE_MIN_CAPACITY_MW = 50.0
BRITISH_NATIONAL_GRID = "EPSG:27700"  # REPD coordinates, Northern Ireland included (REPD Definition Sheet)

IFS_STEPS = (*range(0, 145, 3), *range(150, 361, 6))  # 00z and 12z runs


@dataclass(frozen=True)
class Dataset:
    resource: str
    model: str  # portal path segment
    resolution: str
    stream: str
    type: str
    steps: Mapping[int, tuple[int, ...]]  # run hour (UTC) -> forecast steps (hours) published

    def file_url(self, run: datetime, step: int, extension: str) -> str:
        return (
            f"{BASE_URL}/{run:%Y%m%d}/{run:%H}z/{self.model}/{self.resolution}/{self.stream}/"
            f"{run:%Y%m%d%H}0000-{step}h-{self.stream}-{self.type}.{extension}"
        )


DATASETS = (Dataset("ecmwf__ifs_oper", "ifs", "0p25", "oper", "fc", {0: IFS_STEPS, 12: IFS_STEPS}),)


@dataclass(frozen=True)
class GridPoint:
    index: int
    latitude: float
    longitude: float


def run_times(dataset: Dataset, days: DateRange) -> Iterator[datetime]:
    for chunk in days.chunks(1):
        for hour in sorted(dataset.steps):
            yield datetime(chunk.first.year, chunk.first.month, chunk.first.day, hour, tzinfo=UTC)


def run_stamp(run: datetime) -> str:
    return f"{run:%Y%m%d%H}"


def as_cursor(day: date) -> int:
    return int(f"{day:%Y%m%d}")


# --- sites --------------------------------------------------------------------------------------


def select_sites(rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Operational wind and solar sites of at least 50 MW, with WGS84 coordinates."""
    chosen = []
    for row in rows:
        capacity = _number(row.get("Installed Capacity (MWelec)"))
        x, y = _number(row.get("X-coordinate")), _number(row.get("Y-coordinate"))
        if (
            row.get("Development Status (short)") == SITE_STATUS
            and row.get("Technology Type") in SITE_TECHNOLOGIES
            and capacity is not None
            and capacity >= SITE_MIN_CAPACITY_MW
            and x is not None
            and y is not None
        ):
            chosen.append({"ref_id": row["Ref ID"], "x": x, "y": y})
    return [
        {"ref_id": site["ref_id"], "latitude": latitude, "longitude": longitude}
        for site, (latitude, longitude) in zip(chosen, to_wgs84(chosen), strict=True)
    ]


def to_wgs84(sites: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """(latitude, longitude) of British National Grid eastings / northings, with DuckDB's spatial extension."""
    if not sites:
        return []
    with duckdb.connect() as con:
        con.install_extension("spatial")
        con.load_extension("spatial")
        con.execute("create table site (n integer, x double, y double)")
        con.executemany("insert into site values (?, ?, ?)", [(n, s["x"], s["y"]) for n, s in enumerate(sites)])
        rows = con.execute(
            f"select ST_Y(p), ST_X(p) from (select n, ST_Transform(ST_Point(x, y), '{BRITISH_NATIONAL_GRID}',"
            " 'EPSG:4326', always_xy := true) as p from site) order by n"
        ).fetchall()
    return [(float(latitude), float(longitude)) for latitude, longitude in rows]


def current_sites() -> list[dict[str, Any]]:
    """The sites of the REPD's current extract, re-derived only when the extract changes."""
    state = dlt.current.resource_state()
    previous = state.get("sites", {})
    url = desnz_repd.current_extract_url()
    etag = previous.get("etag") if previous.get("url") == url else None
    text, validators = http.fetch_if_changed(url, etag=etag or None, encoding=desnz_repd.ENCODING)
    if text is None:
        return previous["sites"]
    sites = select_sites(desnz_repd.parse_extract(text))
    state["sites"] = {"url": url, "etag": validators.get("etag"), "sites": sites}
    logger.info("%d sites from %s", len(sites), url)
    return sites


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


# --- fields ---------------------------------------------------------------------------------------


def field_ranges(index_text: str) -> list[tuple[int, int]]:
    """Byte ranges (first, last inclusive) of the surface fields in `PARAMS`, from a step's index."""
    entries = (json.loads(line) for line in index_text.splitlines() if line.strip())
    return sorted(
        (entry["_offset"], entry["_offset"] + entry["_length"] - 1)
        for entry in entries
        if entry.get("param") in PARAMS and entry.get("levtype") == "sfc"
    )


def fetch_step(dataset: Dataset, run: datetime, step: int) -> list[bytes]:
    """The GRIB messages of one step's fields."""
    index = http.fetch_bytes(dataset.file_url(run, step, "index"))
    if index is None:
        raise RuntimeError(f"{dataset.resource}: step {step} of the {run:%Y-%m-%d %H}z run is not published")
    grib_url = dataset.file_url(run, step, "grib2")
    messages = []
    for byte_range in field_ranges(index.decode()):
        content = http.fetch_bytes(grib_url, byte_range)
        if content is None:
            raise RuntimeError(f"{grib_url}: not published")
        messages.append(content)
    return messages


def nearest_points(handle: Any, sites: list[dict[str, Any]]) -> list[GridPoint]:
    """The distinct grid points nearest to the sites (eccodes' nearest neighbour)."""
    points = {}
    for site in sites:
        nearest = eccodes.codes_grib_find_nearest(handle, site["latitude"], site["longitude"])[0]
        points[int(nearest["index"])] = GridPoint(int(nearest["index"]), float(nearest["lat"]), float(nearest["lon"]))
    return sorted(points.values(), key=lambda point: point.index)


def grid_signature(handle: Any) -> tuple[Any, ...]:
    keys = ("gridType", "Ni", "Nj", "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees")
    return tuple(eccodes.codes_get(handle, key) for key in keys)


def field_rows(
    message: bytes, sites: list[dict[str, Any]], grids: dict[tuple[Any, ...], list[GridPoint]]
) -> list[dict[str, Any]]:
    """One row per grid point: the field's GRIB keys, the point and its value as published."""
    handle = eccodes.codes_new_from_message(message)
    try:
        grid = grid_signature(handle)
        if grid not in grids:
            grids[grid] = nearest_points(handle, sites)
        points = grids[grid]
        keys = {key: eccodes.codes_get(handle, key) for key in GRIB_KEYS}
        values = eccodes.codes_get_double_elements(handle, "values", [point.index for point in points])
        missing = eccodes.codes_get(handle, "missingValue") if eccodes.codes_get(handle, "bitmapPresent") else None
        return [
            {
                **keys,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "value": None if value == missing else value,
            }
            for point, value in zip(points, values, strict=True)
        ]
    finally:
        eccodes.codes_release(handle)


def fetched_in_order[T](pool: Executor, fetch: Callable[[int], T], steps: Iterable[int]) -> Iterator[T]:
    """`fetch` of each step, in order, with at most `FETCH_WORKERS` steps in flight (memory stays at batch size)."""
    pending: deque[Future[T]] = deque()
    for step in steps:
        pending.append(pool.submit(fetch, step))
        if len(pending) >= FETCH_WORKERS:
            yield pending.popleft().result()
    while pending:
        yield pending.popleft().result()


def fetch_run(dataset: Dataset, run: datetime, sites: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    """A complete run's rows, in pages; nothing while its last step is not published."""
    steps = dataset.steps[run.hour]
    if http.fetch_bytes(dataset.file_url(run, steps[-1], "index")) is None:
        logger.info("%s: %s not complete or no longer published", dataset.resource, run_stamp(run))
        return
    started, grids, page, total = time.monotonic(), {}, [], 0
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        for messages in fetched_in_order(pool, lambda step: fetch_step(dataset, run, step), steps):
            for message in messages:
                page.extend(field_rows(message, sites, grids))
            if len(page) >= PAGE_ROWS:
                total += len(page)
                yield page
                page = []
    if page:
        total += len(page)
        yield page
    logger.info("%s: %s, %d rows in %.1f s", dataset.resource, run_stamp(run), total, time.monotonic() - started)


def stream(dataset: Dataset, window: RunWindow) -> DltResource:
    initial_value = as_cursor(window.start)
    end_value = as_cursor(window.end + timedelta(days=1)) if window.end else None

    @dlt.resource(
        name=dataset.resource,
        write_disposition=SCD2,
        primary_key=NATURAL_KEY,
        merge_key=NATURAL_KEY,
        file_format="parquet",
    )
    def rows(
        # no row hashes at the cursor date (a run is ~56k rows): repeats merge on the natural key
        cursor: dlt.sources.incremental[int] = dlt.sources.incremental(
            CURSOR, initial_value=initial_value, end_value=end_value, primary_key=()
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        days = incremental_window(cursor, window.max_days, revisit_days=REVISIT_DAYS)
        sites = current_sites()
        state = dlt.current.resource_state()
        loaded: list[str] = state.get("runs_loaded", [])
        for run in run_times(dataset, days):
            if cursor.end_value is None and run_stamp(run) in loaded:
                continue
            published = False
            for page in fetch_run(dataset, run, sites):
                published = True
                yield page
            if published and cursor.end_value is None:
                loaded = [*loaded, run_stamp(run)][-RUNS_REMEMBERED:]
                state["runs_loaded"] = loaded

    return rows


@dlt.source(name="ecmwf")
def ecmwf_source(window: RunWindow) -> list[DltResource]:
    return [stream(dataset, window) for dataset in DATASETS]


SPEC = SourceSpec("ecmwf", ecmwf_source, requires=("desnz_repd",))  # dim_site
