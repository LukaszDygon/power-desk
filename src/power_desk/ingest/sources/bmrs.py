"""Elexon Insights Solution (BMRS) datasets, as streams.

Each dataset is fetched by publish time, one day per request, from its incremental cursor
(`publishTime`); records are stored as published and merged on their natural key. A failed
request fails the run, so the cursor never moves past a gap. Settlement dates are UK-local, so
requested date ranges are padded by a day.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import logging
from typing import Any

import dlt
from dlt.sources import DltResource

from power_desk.ingest import http
from power_desk.ingest.spec import RunWindow, SourceSpec
from power_desk.ingest.windows import DateRange, day_after, incremental_window

logger = logging.getLogger(__name__)

API_BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
MAX_DAYS_PER_RUN = 7


@dataclass(frozen=True)
class Dataset:
    resource: str
    code: str  # Elexon dataset code
    primary_key: tuple[str, ...]


DATASETS = (
    Dataset("bmrs__fuelinst", "FUELINST", ("settlementDate", "settlementPeriod", "fuelType", "startTime")),
    Dataset("bmrs__indo", "INDO", ("settlementDate", "settlementPeriod")),
    Dataset("bmrs__itsdo", "ITSDO", ("settlementDate", "settlementPeriod")),
    Dataset("bmrs__ndf", "NDF", ("settlementDate", "settlementPeriod", "publishTime")),
    Dataset("bmrs__windfor", "WINDFOR", ("startTime", "publishTime")),
)


def fetch_published(dataset: Dataset, days: DateRange) -> list[dict[str, Any]]:
    """Records published from `days.first` 00:00 to `days.last` 23:59:59 UTC."""
    logger.info("%s: %s..%s", dataset.resource, days.first, days.last)
    payload = http.fetch_json(
        f"{API_BASE}/{dataset.code}",
        params={
            "publishDateTimeFrom": f"{days.first.isoformat()}T00:00:00Z",
            "publishDateTimeTo": f"{days.last.isoformat()}T23:59:59Z",
        },
    )
    return payload.get("data", []) if isinstance(payload, dict) else payload


def stream(dataset: Dataset, window: RunWindow) -> DltResource:
    initial_value = window.start.isoformat()
    end_value = day_after(window.end) if window.end else None

    @dlt.resource(name=dataset.resource, write_disposition="merge", primary_key=list(dataset.primary_key))
    def records(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            "publishTime", initial_value=initial_value, end_value=end_value
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for day in incremental_window(cursor, window.max_days).chunks(days=1):
            if published := fetch_published(dataset, day):
                yield published

    return records


@dlt.source(name="bmrs")
def bmrs_source(window: RunWindow) -> list[DltResource]:
    return [stream(dataset, window) for dataset in DATASETS]


SPEC = SourceSpec("bmrs", bmrs_source, max_days_per_run=MAX_DAYS_PER_RUN, window_padding_days=1)
