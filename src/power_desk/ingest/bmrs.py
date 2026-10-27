"""Elexon BMRS DLT Source Builder.

Extracts raw energy data from the Elexon Insights Solution (BMRS) API
with strict raw data preservation (no row-level transformation in Python),
incremental cursor tracking, and merge write disposition on Natural Keys.

Resources follow the shared contract in `ingest/common.py`; BMRS windows are publish-time
based, and settlement dates are local (Europe/London), hence `window_padding_days=1`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import logging
from typing import Any, Callable, Iterator

import dlt
from dlt.sources import DltResource, DltSource

from power_desk.ingest import common
from power_desk.ingest.common import SourceSpec, day_after, incremental_window, iter_day_windows

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"
DEFAULT_MAX_DAYS_PER_RUN = 7


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
    lag: int = 0  # Pointer lag in seconds (0 = zero lag, immediate continuation)
    extra_params: dict[str, Any] = field(default_factory=dict)
    format_date_from: Callable[[date], str] = lambda d: f"{d.isoformat()}T00:00:00Z"
    format_date_to: Callable[[date], str] = lambda d: f"{d.isoformat()}T23:59:59Z"


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

    def fetch_window(self, config: BmrsResourceConfig, first_day: date, last_day: date) -> list[dict[str, Any]]:
        """Fetch one publish-time window and return the API records untouched."""
        params = {
            config.date_param_from: config.format_date_from(first_day),
            config.date_param_to: config.format_date_to(last_day),
            **config.extra_params,
        }
        logger.info("Extracting %s %s..%s", config.name, first_day, last_day)
        payload = common.fetch_json(f"{self.api_base}{config.endpoint}", params=params)
        if isinstance(payload, dict) and config.records_path:
            return payload.get(config.records_path, [])
        return payload if isinstance(payload, list) else []

    def _create_resource_generator(
        self,
        config: BmrsResourceConfig,
        initial_date: str,
        end_date: str | None,
        max_days_per_run: int,
    ) -> Callable[..., Iterator[list[dict[str, Any]]]]:
        builder = self

        def resource_gen(
            cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
                config.cursor_field,
                initial_value=initial_date,
                end_value=day_after(end_date) if end_date else None,
                lag=config.lag,
            ),
        ) -> Iterator[list[dict[str, Any]]]:
            first_day, last_day = incremental_window(cursor, max_days_per_run)
            for window_start, window_end in iter_day_windows(first_day, last_day, config.default_step_days):
                # Errors propagate on purpose: a skipped window would advance the
                # cursor past a gap. A failed run commits no state and is retried.
                records = builder.fetch_window(config, window_start, window_end)
                if records:
                    yield records

        return resource_gen

    def build(
        self,
        source_name: str = "bmrs",
        initial_date: str = "2024-01-01",
        end_date: str | None = None,
        max_days_per_run: int = DEFAULT_MAX_DAYS_PER_RUN,
    ) -> DltSource:
        """Builds the dlt source with all registered resources."""
        resources: list[DltResource] = [
            dlt.resource(
                self._create_resource_generator(config, initial_date, end_date, max_days_per_run),
                name=config.name,
                write_disposition="merge",
                primary_key=config.primary_key,
            )
            for config in self.configs.values()
        ]

        @dlt.source(name=source_name)
        def _source() -> list[DltResource]:
            return resources

        return _source()


def get_default_builder(api_base: str = DEFAULT_API_BASE) -> BmrsSourceBuilder:
    """Instantiate a BmrsSourceBuilder configured with the core UK energy datasets."""
    builder = BmrsSourceBuilder(api_base=api_base)

    builder.add_resource(
        BmrsResourceConfig(
            name="raw_fuelinst",
            endpoint="/datasets/FUELINST",
            primary_key=["settlementDate", "settlementPeriod", "fuelType", "startTime"],
        )
    )
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_indo",
            endpoint="/datasets/INDO",
            primary_key=["settlementDate", "settlementPeriod"],
        )
    )
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_itsdo",
            endpoint="/datasets/ITSDO",
            primary_key=["settlementDate", "settlementPeriod"],
        )
    )
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_demand_forecast",
            endpoint="/datasets/NDF",
            primary_key=["settlementDate", "settlementPeriod", "publishTime"],
        )
    )
    builder.add_resource(
        BmrsResourceConfig(
            name="raw_windfor",
            endpoint="/datasets/WINDFOR",
            primary_key=["startTime", "publishTime"],
        )
    )
    return builder



def build_default_bmrs_source(
    initial_date: str = "2024-01-01",
    end_date: str | None = None,
    max_days_per_run: int = DEFAULT_MAX_DAYS_PER_RUN,
    api_base: str = DEFAULT_API_BASE,
) -> DltSource:
    """Convenience helper to obtain the default Elexon BMRS source."""
    return get_default_builder(api_base=api_base).build(
        source_name="bmrs",
        initial_date=initial_date,
        end_date=end_date,
        max_days_per_run=max_days_per_run,
    )


SPEC = SourceSpec("bmrs", build_default_bmrs_source, max_days_per_run=DEFAULT_MAX_DAYS_PER_RUN, window_padding_days=1)
