"""Sheffield Solar PVLive: GB national solar generation outturn (PES region 0), as a stream.

One row per half hour, keyed on the half-hour *ending* time `datetime_gmt` (the cursor).
Settlement dates downstream are UK-local, so requested date ranges are padded by a day.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
import logging
from typing import Any

import dlt
from dlt.sources import DltResource

from power_desk.ingest import http
from power_desk.ingest.spec import SourceSpec
from power_desk.ingest.windows import day_after, day_windows, incremental_window

logger = logging.getLogger(__name__)

API_URL = "https://api.pvlive.uk/pvlive/api/v4/pes/0"
MAX_DAYS_PER_RUN = 31
DAYS_PER_REQUEST = 7


def fetch_half_hours(first_day: date, last_day: date) -> list[dict[str, Any]]:
    """Half hours ending from `first_day` 00:30 to `last_day + 1` 00:00 UTC."""
    logger.info("pvlive__solar: %s..%s", first_day, last_day)
    payload = http.fetch_json(
        API_URL,
        params={
            "start": f"{first_day.isoformat()}T00:30:00Z",
            "end": f"{(last_day + timedelta(days=1)).isoformat()}T00:00:00Z",
        },
    )
    columns = payload.get("meta", ["pes_id", "datetime_gmt", "generation_mw"])
    return [dict(zip(columns, row, strict=False)) for row in payload.get("data", [])]


@dlt.source(name="pvlive")
def pvlive_source(
    initial_date: str, end_date: str | None = None, max_days_per_run: int = MAX_DAYS_PER_RUN
) -> DltResource:
    end_value = f"{day_after(end_date)}T00:30:00Z" if end_date else None  # half-hour ending: a day ends at D+1 00:00

    @dlt.resource(name="pvlive__solar", write_disposition="merge", primary_key=["pes_id", "datetime_gmt"])
    def solar(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            "datetime_gmt",
            initial_value=initial_date,
            end_value=end_value,
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for first_day, last_day in day_windows(*incremental_window(cursor, max_days_per_run), DAYS_PER_REQUEST):
            if half_hours := fetch_half_hours(first_day, last_day):
                yield half_hours

    return solar


SPEC = SourceSpec("pvlive", pvlive_source, max_days_per_run=MAX_DAYS_PER_RUN, window_padding_days=1)
