"""Elexon BMRS DLT Source Builder.

Extracts raw energy data from the Elexon Insights Solution (BMRS) API
with strict raw data preservation (no row-level transformation in Python),
incremental cursor tracking, and merge write disposition on Natural Keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any, Callable, Generator, Iterable
import urllib.parse
import urllib.request
import json

import dlt
from dlt.sources import DltResource, DltSource

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"


@dataclass
class BmrsResourceConfig:
    """Configuration for an individual Elexon BMRS dataset resource."""

    name: str
    endpoint: str
    primary_key: list[str]
    date_param_from: str = "publishDateTimeFrom"
    date_param_to: str = "publishDateTimeTo"
    cursor_field: str = "publishTime"
    records_path: str | None = "data"
    default_step_days: int = 1
    lag: int = 0  # Pointer lag in seconds or units (0 = zero lag, immediate continuation)
    extra_params: dict[str, Any] = field(default_factory=dict)
    format_date_from: Callable[[datetime | date], str] = lambda d: f"{d.strftime('%Y-%m-%d')}T00:00:00Z"
    format_date_to: Callable[[datetime | date], str] = lambda d: f"{d.strftime('%Y-%m-%d')}T23:59:59Z"
    include_solar: bool = False


def fetch_bmrs_json(url: str, timeout: int = 20) -> Any:
    """Fetch raw JSON from Elexon BMRS API with standard user agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PowerDesk/1.0 (Analyst Terminal)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)


def fetch_pvlive_solar(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Fetch official GB national solar generation outturn from Sheffield Solar PVLive."""
    # PVLive uses half-hour ending timestamps (datetime_gmt).
    # For a settlement day, period 1 ends at 00:30:00Z and period 48 ends at 00:00:00Z the next day.
    try:
        start_dt_day = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        end_dt_day = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        next_day = end_dt_day + timedelta(days=1)

        start_iso = f"{start_dt_day.strftime('%Y-%m-%d')}T00:30:00Z"
        end_iso = f"{next_day.strftime('%Y-%m-%d')}T00:00:00Z"
        url = f"https://api.pvlive.uk/pvlive/api/v4/pes/0?start={start_iso}&end={end_iso}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PowerDesk/1.0 (Analyst Terminal)", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_records = data.get("data", [])
            solar_records = []
            for rec in raw_records:
                # rec is [pes_id, datetime_gmt, generation_mw]
                dt_str = rec[1]
                gen_mw = float(rec[2]) if rec[2] is not None else 0.0
                gen_val = int(round(gen_mw))
                dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
                start_dt = dt - timedelta(minutes=30)
                settlement_date = start_dt.strftime("%Y-%m-%d")
                period = start_dt.hour * 2 + (1 if start_dt.minute == 0 else 2)

                # Expand 30-min settlement period into 6 5-minute ticks
                # to align with 5-minute FUELINST data and primary key
                for min_offset in (0, 5, 10, 15, 20, 25):
                    tick_dt = start_dt + timedelta(minutes=min_offset)
                    solar_records.append({
                        "dataset": "PVLIVE",
                        "publishTime": dt_str,
                        "startTime": tick_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "settlementDate": settlement_date,
                        "settlementPeriod": period,
                        "fuelType": "SOLAR",
                        "generation": gen_val,
                    })
            return solar_records
    except Exception as exc:
        logger.warning("Failed to fetch PVLive solar for %s to %s: %s", start_date, end_date, exc)
        return []


class BmrsSourceBuilder:
    """Configurable builder for Elexon BMRS DLT sources.

    Allows adding resources via configuration objects and builds a DltSource
    with incremental merge write disposition and preserved raw payloads.
    """

    def __init__(self, api_base: str = DEFAULT_API_BASE) -> None:
        self.api_base = api_base.rstrip("/")
        self.configs: dict[str, BmrsResourceConfig] = {}

    def add_resource(self, config: BmrsResourceConfig) -> BmrsSourceBuilder:
        """Register a new BMRS resource configuration."""
        self.configs[config.name] = config
        return self

    def _create_resource_generator(
        self,
        config: BmrsResourceConfig,
        initial_date: str,
        end_date: str | None = None,
    ) -> Callable[..., Generator[list[dict[str, Any]], None, None]]:
        """Creates an incremental generator function that runs until data ends and stores the pointer."""

        if end_date:
            # Bounded historical backfill: extracts exact range and merges on natural key
            def bounded_resource_gen() -> Generator[list[dict[str, Any]], None, None]:
                start_dt = datetime.strptime(initial_date[:10], "%Y-%m-%d").date()
                max_dt = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
                curr_dt = start_dt
                step = timedelta(days=config.default_step_days)

                logger.info("Starting bounded backfill for %s from %s to %s", config.name, curr_dt, max_dt)
                while curr_dt <= max_dt:
                    chunk_end = min(curr_dt + step - timedelta(days=1), max_dt)
                    params: dict[str, Any] = {
                        config.date_param_from: config.format_date_from(curr_dt),
                        config.date_param_to: config.format_date_to(chunk_end),
                        **config.extra_params,
                    }
                    query_str = urllib.parse.urlencode(params)
                    url = f"{self.api_base}{config.endpoint}?{query_str}"
                    try:
                        logger.info("Extracting %s from %s", config.name, url)
                        payload = fetch_bmrs_json(url)
                        records: list[dict[str, Any]] = []
                        if isinstance(payload, dict) and config.records_path:
                            records = payload.get(config.records_path, [])
                        elif isinstance(payload, list):
                            records = payload

                        if config.name == "raw_demand_forecast":
                            for rec in records:
                                if "demand" in rec and "national_demand" not in rec:
                                    rec["national_demand"] = rec["demand"]

                        if config.include_solar:
                            solar_recs = fetch_pvlive_solar(
                                curr_dt.strftime("%Y-%m-%d"),
                                chunk_end.strftime("%Y-%m-%d"),
                            )
                            logger.info("Fetched %d solar records from PVLive", len(solar_recs))
                            records.extend(solar_recs)

                        if records:
                            yield records
                    except Exception as exc:
                        logger.warning("Failed to fetch %s for %s: %s", config.name, curr_dt, exc)
                    curr_dt += step

            return bounded_resource_gen

        # Open-ended incremental run: starts from pointer, runs until data ends, stores latest pointer (lag=0)
        def incremental_resource_gen(
            cursor_val: dlt.sources.incremental[str] = dlt.sources.incremental(
                config.cursor_field,
                initial_value=initial_date,
                lag=config.lag,
            ),
        ) -> Generator[list[dict[str, Any]], None, None]:
            raw_start = cursor_val.last_value or initial_date
            if "T" in str(raw_start):
                start_dt = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00")).date()
            else:
                start_dt = datetime.strptime(str(raw_start)[:10], "%Y-%m-%d").date()

            max_dt = date.today() + timedelta(days=2)
            curr_dt = start_dt
            step = timedelta(days=config.default_step_days)

            logger.info(
                "Starting incremental run for %s from pointer=%s (start_date=%s) to max_dt=%s (lag=%s)",
                config.name,
                cursor_val.last_value,
                curr_dt,
                max_dt,
                config.lag,
            )

            empty_chunks = 0
            while curr_dt <= max_dt:
                chunk_end = min(curr_dt + step - timedelta(days=1), max_dt)
                params: dict[str, Any] = {
                    config.date_param_from: config.format_date_from(curr_dt),
                    config.date_param_to: config.format_date_to(chunk_end),
                    **config.extra_params,
                }

                query_str = urllib.parse.urlencode(params)
                url = f"{self.api_base}{config.endpoint}?{query_str}"

                try:
                    logger.info("Extracting %s from %s", config.name, url)
                    payload = fetch_bmrs_json(url)
                    records: list[dict[str, Any]] = []

                    if isinstance(payload, dict) and config.records_path:
                        records = payload.get(config.records_path, [])
                    elif isinstance(payload, list):
                        records = payload

                    if config.name == "raw_demand_forecast":
                        for rec in records:
                            if "demand" in rec and "national_demand" not in rec:
                                rec["national_demand"] = rec["demand"]

                    if config.include_solar:
                        solar_recs = fetch_pvlive_solar(
                            curr_dt.strftime("%Y-%m-%d"),
                            chunk_end.strftime("%Y-%m-%d"),
                        )
                        logger.info("Fetched %d solar records from PVLive", len(solar_recs))
                        records.extend(solar_recs)

                    if records:
                        empty_chunks = 0
                        # Yield raw records as-is. dlt inspects cursor_field and advances cursor_val.last_value!
                        yield records
                    else:
                        empty_chunks += 1
                        # If end of data reached near current date, stop extraction and keep latest pointer
                        if curr_dt >= date.today() - timedelta(days=1):
                            logger.info(
                                "No further records returned for %s at %s. Storing pointer to latest value: %s",
                                config.name,
                                curr_dt,
                                cursor_val.last_value,
                            )
                            break

                except urllib.error.HTTPError as http_err:
                    if http_err.code in (404, 400) and curr_dt >= date.today() - timedelta(days=1):
                        logger.info(
                            "Data stream reached end (%s) for %s at %s. Latest stored pointer: %s",
                            http_err,
                            config.name,
                            curr_dt,
                            cursor_val.last_value,
                        )
                        break
                    logger.warning("HTTP error fetching %s for %s: %s", config.name, curr_dt, http_err)
                except Exception as exc:
                    logger.warning("Failed to fetch %s for %s: %s", config.name, curr_dt, exc)

                curr_dt += step

        return incremental_resource_gen

    def build(
        self,
        source_name: str = "bmrs",
        initial_date: str = "2024-01-01",
        end_date: str | None = None,
    ) -> DltSource:
        """Builds the dlt source with all registered resources."""
        resources: list[DltResource] = []

        for name, config in self.configs.items():
            gen_fn = self._create_resource_generator(config, initial_date, end_date)
            # Decorate dynamically as a dlt resource with merge write disposition
            res = dlt.resource(
                gen_fn,
                name=config.name,
                write_disposition="merge",
                primary_key=config.primary_key,
            )
            resources.append(res)

        @dlt.source(name=source_name)
        def _source() -> Iterable[DltResource]:
            return resources

        return _source()


def get_default_builder(api_base: str = DEFAULT_API_BASE) -> BmrsSourceBuilder:
    """Instantiate a BmrsSourceBuilder configured with the core UK energy datasets."""
    builder = BmrsSourceBuilder(api_base=api_base)

    # 1. Fuel Generation Mix Outturn (FUELINST + Sheffield Solar PVLive)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_fuelinst",
            endpoint="/datasets/FUELINST",
            primary_key=["settlementDate", "settlementPeriod", "fuelType", "startTime"],
            date_param_from="publishDateTimeFrom",
            date_param_to="publishDateTimeTo",
            cursor_field="publishTime",
            include_solar=True,
            default_step_days=1,
        )
    )

    # 2. Initial National Demand Outturn (INDO)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_indo",
            endpoint="/datasets/INDO",
            primary_key=["settlementDate", "settlementPeriod"],
            date_param_from="publishDateTimeFrom",
            date_param_to="publishDateTimeTo",
            cursor_field="publishTime",
            default_step_days=1,
        )
    )

    # 3. Initial Transmission System Demand Outturn (ITSDO)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_itsdo",
            endpoint="/datasets/ITSDO",
            primary_key=["settlementDate", "settlementPeriod"],
            date_param_from="publishDateTimeFrom",
            date_param_to="publishDateTimeTo",
            cursor_field="publishTime",
            default_step_days=1,
        )
    )

    # 4. National Demand Forecast (NDF)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_demand_forecast",
            endpoint="/datasets/NDF",
            primary_key=["settlementDate", "settlementPeriod", "publishTime"],
            date_param_from="publishDateTimeFrom",
            date_param_to="publishDateTimeTo",
            cursor_field="publishTime",
            default_step_days=1,
        )
    )

    # 5. Day-Ahead Wind Generation Forecast (WINDFOR)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_windfor",
            endpoint="/datasets/WINDFOR",
            primary_key=["startTime", "publishTime"],
            date_param_from="publishDateTimeFrom",
            date_param_to="publishDateTimeTo",
            cursor_field="publishTime",
            default_step_days=1,
        )
    )

    return builder


def build_default_bmrs_source(
    initial_date: str = "2024-01-01",
    end_date: str | None = None,
    api_base: str = DEFAULT_API_BASE,
) -> DltSource:
    """Convenience helper to obtain the default Elexon BMRS source."""
    builder = get_default_builder(api_base=api_base)
    return builder.build(
        source_name="bmrs",
        initial_date=initial_date,
        end_date=end_date,
    )
