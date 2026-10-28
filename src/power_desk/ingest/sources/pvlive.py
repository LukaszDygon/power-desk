"""Sheffield Solar PVLive: GB national solar generation outturn (PES region 0), as a stream.

One row per half hour, keyed on the half-hour *ending* time `datetime_gmt` (the cursor).
Settlement dates downstream are UK-local, so requested date ranges are padded by a day.
"""

from __future__ import annotations

from collections.abc import Iterator
import logging
from typing import Any

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltResource

from power_desk.ingest import http
from power_desk.ingest.spec import RunWindow, SourceSpec
from power_desk.ingest.windows import DateRange, day_after, incremental_window

logger = logging.getLogger(__name__)

API_URL = "https://api.pvlive.uk/pvlive/api/v4/pes/0"
MAX_DAYS_PER_RUN = 31
DAYS_PER_REQUEST = 7
UPSERT: TMergeDispositionDict = {"disposition": "merge", "strategy": "upsert"}  # `_dlt_id` from the primary key


def fetch_half_hours(days: DateRange) -> list[dict[str, Any]]:
    """Half hours ending from `days.first` 00:30 to `days.last + 1` 00:00 UTC."""
    logger.info("pvlive__solar: %s..%s", days.first, days.last)
    payload = http.fetch_json(
        API_URL,
        params={
            "start": f"{days.first.isoformat()}T00:30:00Z",
            "end": f"{day_after(days.last)}T00:00:00Z",
        },
    )
    columns = payload.get("meta", ["pes_id", "datetime_gmt", "generation_mw"])
    return [dict(zip(columns, row, strict=False)) for row in payload.get("data", [])]


@dlt.source(name="pvlive")
def pvlive_source(window: RunWindow) -> DltResource:
    initial_value = window.start.isoformat()
    # half-hour ending: a day ends at D+1 00:00
    end_value = f"{day_after(window.end)}T00:30:00Z" if window.end else None

    @dlt.resource(
        name="pvlive__solar", write_disposition=UPSERT, primary_key=["pes_id", "datetime_gmt"], file_format="parquet"
    )
    def solar(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            "datetime_gmt",
            initial_value=initial_value,
            end_value=end_value,
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for days in incremental_window(cursor, window.max_days).chunks(DAYS_PER_REQUEST):
            if half_hours := fetch_half_hours(days):
                yield half_hours

    return solar


SPEC = SourceSpec("pvlive", pvlive_source, max_days_per_run=MAX_DAYS_PER_RUN, window_padding_days=1)
