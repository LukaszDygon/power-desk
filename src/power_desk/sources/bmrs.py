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
    date_param_from: str = "settlementDateFrom"
    date_param_to: str = "settlementDateTo"
    cursor_field: str = "settlementDate"
    records_path: str | None = "data"
    default_step_days: int = 1
    extra_params: dict[str, Any] = field(default_factory=dict)
    format_date: Callable[[datetime | date], str] = lambda d: d.strftime("%Y-%m-%d")


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
        """Creates a generator function for a specific resource configuration."""

        def resource_gen(
            cursor_val: dlt.sources.incremental[str] = dlt.sources.incremental(
                config.cursor_field,
                initial_value=initial_date,
            ),
        ) -> Generator[list[dict[str, Any]], None, None]:
            # Determine start date from cursor
            raw_start = cursor_val.last_value or initial_date
            if "T" in str(raw_start):
                start_dt = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00")).date()
            else:
                start_dt = datetime.strptime(str(raw_start)[:10], "%Y-%m-%d").date()

            if end_date:
                end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
            else:
                # Default to today
                end_dt = date.today()

            curr_dt = start_dt
            step = timedelta(days=config.default_step_days)

            while curr_dt <= end_dt:
                chunk_end = min(curr_dt + step - timedelta(days=1), end_dt)
                params: dict[str, Any] = {
                    config.date_param_from: config.format_date(curr_dt),
                    config.date_param_to: config.format_date(chunk_end),
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

                    if records:
                        # Yield raw records as-is. No custom row processing!
                        yield records

                except Exception as exc:
                    logger.warning("Failed to fetch %s for %s: %s", config.name, curr_dt, exc)

                curr_dt += step

        return resource_gen

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

    # 1. Fuel Generation Mix Outturn (FUELINST)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_fuelinst",
            endpoint="/datasets/FUELINST",
            primary_key=["settlementDate", "settlementPeriod", "fuelType", "startTime"],
            date_param_from="publishDateTimeFrom",
            date_param_to="publishDateTimeTo",
            cursor_field="publishTime",
            format_date=lambda d: f"{d.strftime('%Y-%m-%d')}T00:00:00Z",
            default_step_days=1,
        )
    )

    # 2. Initial National Demand Outturn (INDO)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_indo",
            endpoint="/datasets/INDO",
            primary_key=["settlementDate", "settlementPeriod"],
            date_param_from="settlementDateFrom",
            date_param_to="settlementDateTo",
            cursor_field="settlementDate",
            default_step_days=7,
        )
    )

    # 3. Initial Transmission System Demand Outturn (ITSDO)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_itsdo",
            endpoint="/datasets/ITSDO",
            primary_key=["settlementDate", "settlementPeriod"],
            date_param_from="settlementDateFrom",
            date_param_to="settlementDateTo",
            cursor_field="settlementDate",
            default_step_days=7,
        )
    )

    # 4. Day-Ahead Demand Forecast (forecast/demand/day-ahead)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_demand_forecast",
            endpoint="/forecast/demand/day-ahead",
            primary_key=["settlementDate", "settlementPeriod", "boundary", "publishTime"],
            date_param_from="settlementDate",
            date_param_to="settlementDate",
            cursor_field="settlementDate",
            default_step_days=1,
        )
    )

    # 5. Day-Ahead Wind Generation Forecast (WINDFOR)
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_windfor",
            endpoint="/datasets/WINDFOR",
            primary_key=["startTime", "publishTime"],
            date_param_from="settlementDateFrom",
            date_param_to="settlementDateTo",
            cursor_field="publishTime",
            default_step_days=7,
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
