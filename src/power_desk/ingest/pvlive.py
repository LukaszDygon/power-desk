"""Sheffield Solar PVLive DLT source.

GB national solar generation outturn (PES region 0), stored as published:
one row per half hour, keyed on the half-hour *ending* timestamp `datetime_gmt`.
Aligning solar with FUELINST's 5-minute grain happens in dbt (`ods_generation_actual`).
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Iterator

import dlt
from dlt.sources import DltSource

from power_desk.ingest import common
from power_desk.ingest.common import SourceSpec, day_after, incremental_window, iter_day_windows

logger = logging.getLogger(__name__)

PVLIVE_URL = "https://api.pvlive.uk/pvlive/api/v4/pes/0"
DEFAULT_MAX_DAYS_PER_RUN = 31
STEP_DAYS = 7


def fetch_pvlive_window(first_day, last_day) -> list[dict[str, Any]]:
    """Fetch half-hourly national solar outturn ending within [first_day 00:30, last_day+1 00:00]."""
    params = {
        "start": f"{first_day.isoformat()}T00:30:00Z",
        "end": f"{(last_day + timedelta(days=1)).isoformat()}T00:00:00Z",
    }
    logger.info("Extracting raw_pvlive_solar %s..%s", first_day, last_day)
    payload = common.fetch_json(PVLIVE_URL, params=params)
    columns = payload.get("meta", ["pes_id", "datetime_gmt", "generation_mw"])
    return [dict(zip(columns, row)) for row in payload.get("data", [])]


@dlt.source(name="pvlive")
def pvlive_source(
    initial_date: str = "2024-01-01",
    end_date: str | None = None,
    max_days_per_run: int = DEFAULT_MAX_DAYS_PER_RUN,
) -> Any:
    @dlt.resource(name="raw_pvlive_solar", write_disposition="merge", primary_key=["pes_id", "datetime_gmt"])
    def raw_pvlive_solar(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            "datetime_gmt",
            initial_value=initial_date,
            # Exclusive; half-hour *ending* timestamps put the day's last row at D+1 00:00.
            end_value=f"{day_after(end_date)}T00:30:00Z" if end_date else None,
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        """PVLive: GB national solar generation outturn per half hour (half-hour ending, GMT)."""
        first_day, last_day = incremental_window(cursor, max_days_per_run)
        for window_start, window_end in iter_day_windows(first_day, last_day, STEP_DAYS):
            records = fetch_pvlive_window(window_start, window_end)
            if records:
                yield records

    return raw_pvlive_solar


def build_pvlive_source(
    initial_date: str = "2024-01-01",
    end_date: str | None = None,
    max_days_per_run: int = DEFAULT_MAX_DAYS_PER_RUN,
) -> DltSource:
    return pvlive_source(initial_date=initial_date, end_date=end_date, max_days_per_run=max_days_per_run)


# Settlement dates downstream are UK-local, so fetch windows are padded like BMRS.
SPEC = SourceSpec("pvlive", build_pvlive_source, max_days_per_run=DEFAULT_MAX_DAYS_PER_RUN, window_padding_days=1)
