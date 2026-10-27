"""Elexon Insights Solution (BMRS) datasets, as streams.

Each dataset is fetched by publish time, one day per request, from its incremental cursor
(`publishTime`); records are stored as published and merged on their natural key. A failed
request fails the run, so the cursor never moves past a gap. Settlement dates are UK-local, so
requested date ranges are padded by a day.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
import logging
from typing import Any

import dlt
from dlt.sources import DltResource

from power_desk.ingest import http
from power_desk.ingest.spec import SourceSpec
from power_desk.ingest.windows import day_after, day_windows, incremental_window

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


def fetch_published(dataset: Dataset, first_day: date, last_day: date) -> list[dict[str, Any]]:
    """Records published from `first_day` 00:00 to `last_day` 23:59:59 UTC."""
    logger.info("%s: %s..%s", dataset.resource, first_day, last_day)
    payload = http.fetch_json(
        f"{API_BASE}/{dataset.code}",
        params={
            "publishDateTimeFrom": f"{first_day.isoformat()}T00:00:00Z",
            "publishDateTimeTo": f"{last_day.isoformat()}T23:59:59Z",
        },
    )
    return payload.get("data", []) if isinstance(payload, dict) else payload


def stream(dataset: Dataset, initial_date: str, end_date: str | None, max_days_per_run: int) -> DltResource:
    end_value = day_after(end_date) if end_date else None

    @dlt.resource(name=dataset.resource, write_disposition="merge", primary_key=list(dataset.primary_key))
    def records(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            "publishTime", initial_value=initial_date, end_value=end_value
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for first_day, last_day in day_windows(*incremental_window(cursor, max_days_per_run), step_days=1):
            if published := fetch_published(dataset, first_day, last_day):
                yield published

    return records


@dlt.source(name="bmrs")
def bmrs_source(
    initial_date: str, end_date: str | None = None, max_days_per_run: int = MAX_DAYS_PER_RUN
) -> list[DltResource]:
    return [stream(dataset, initial_date, end_date, max_days_per_run) for dataset in DATASETS]


SPEC = SourceSpec("bmrs", bmrs_source, max_days_per_run=MAX_DAYS_PER_RUN, window_padding_days=1)
