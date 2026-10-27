"""ENTSO-E Transparency Platform data items, as monthly file partitions of the File Library.

The File Library re-exports a month's file daily while its data changes. Each run lists a data
item's folder and loads the files new or changed since their last load (the publisher's
`lastUpdatedTimestamp`, kept in resource state), oldest month first, covering at most
`max_days_per_run` days of months; `capped` is recorded when more changed files remain. A loaded
file replaces every row previously loaded from it (`merge_key` `_source_file`), so revisions and
withdrawals follow the publication. Bounded backfills (`end_date`) load every file in range and
leave the state untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import logging
import re
from typing import Any

import dlt
from dlt.sources import DltResource
import pyarrow as pa
import pyarrow.compute as pc

from power_desk.ingest.sources.entsoe_file_library import SOURCE_FILE, FileLibraryClient, column_name, parse_export
from power_desk.ingest.spec import SourceSpec
from power_desk.ingest.windows import to_date

logger = logging.getLogger(__name__)

PARTITION_REPLACE = {"disposition": "merge", "strategy": "delete-insert"}
FILE_PERIOD = re.compile(r"^(\d{4})_(\d{2})_")
MAX_DAYS_PER_RUN = 186  # about six monthly files per data item and run
MTU_START = column_name("DateTime(UTC)")


@dataclass(frozen=True)
class DataItem:
    resource: str
    folder: str  # <data item>_<Transparency Regulation article>_<release>


DATA_ITEMS = (
    DataItem("entsoe__actual_total_load", "ActualTotalLoad_6.1.A_r3"),
    DataItem("entsoe__day_ahead_total_load_forecast", "DayAheadTotalLoadForecast_6.1.B_r3"),
    DataItem("entsoe__generation_per_type", "AggregatedGenerationPerType_16.1.B_C_r3"),
    DataItem("entsoe__wind_solar_forecast", "GenerationForecastsForWindAndSolar_14.1.D_r3"),
)


def file_period(name: str) -> tuple[date, date] | None:
    """First and last day of the month a `<YYYY>_<MM>_...` file covers."""
    match = FILE_PERIOD.match(name)
    if not match:
        return None
    first = date(int(match[1]), int(match[2]), 1)
    return first, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def plan_files(
    files: list[dict[str, Any]],
    loaded: dict[str, str],
    initial_date: str,
    end_date: str | None,
    max_days_per_run: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Files this run loads, oldest month first, and whether more changed files remain."""
    start, end = to_date(initial_date), to_date(end_date) if end_date else None
    in_range = sorted(
        (
            (period, file)
            for file in files
            if (period := file_period(file["name"])) and period[1] >= start and not (end and period[0] > end)
        ),
        key=lambda candidate: candidate[0],
    )
    if end:
        return [file for _, file in in_range], False
    changed = [
        (period, file) for period, file in in_range if loaded.get(file["name"]) != file.get("lastUpdatedTimestamp")
    ]
    if not changed:
        return [], False
    limit = changed[0][0][0] + timedelta(days=max(max_days_per_run, 1))
    batch = [file for period, file in changed if period[0] < limit]
    return batch, len(batch) < len(changed)


def latest_mtu(table: pa.Table, cursor: str | None) -> str | None:
    latest = pc.max(table[MTU_START]).as_py()
    return max(filter(None, [cursor, latest.isoformat() if latest else None]), default=None)


def file_partitions(
    client: FileLibraryClient,
    item: DataItem,
    initial_date: str,
    end_date: str | None,
    max_days_per_run: int,
) -> Iterator[pa.Table]:
    bounded = end_date is not None
    state = {} if bounded else dlt.current.resource_state()
    loaded: dict[str, str] = state.setdefault("source_files", {})
    batch, capped = plan_files(client.list_folder(item.folder), loaded, initial_date, end_date, max_days_per_run)
    cursor = state.get("last_window", {}).get("cursor_last_value")
    for file in batch:
        logger.info("%s: loading %s (%s bytes zipped)", item.resource, file["name"], file.get("size"))
        table = parse_export(client.download(item.folder, file["name"]), file["name"])
        if table.num_rows:
            cursor = latest_mtu(table, cursor)
            yield table
        loaded[file["name"]] = file.get("lastUpdatedTimestamp")
    if not bounded:
        state["last_window"] = window_record(batch, capped, cursor, state.get("last_window", {}))


def window_record(
    batch: list[dict[str, Any]], capped: bool, cursor: str | None, previous: dict[str, Any]
) -> dict[str, Any]:
    """The run's `last_window`: months covered, `capped`, and the latest market time unit loaded."""
    periods = [file_period(file["name"]) for file in batch]
    return {
        "first_day": periods[0][0].isoformat() if periods else previous.get("first_day"),
        "last_day": periods[-1][1].isoformat() if periods else previous.get("last_day"),
        "capped": capped,
        "files_loaded": len(batch),
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cursor_last_value": cursor,
    }


@dlt.source(name="entsoe")
def entsoe_source(
    initial_date: str, end_date: str | None = None, max_days_per_run: int = MAX_DAYS_PER_RUN
) -> list[DltResource]:
    client = FileLibraryClient()
    return [
        dlt.resource(
            file_partitions(client, item, initial_date, end_date, max_days_per_run),
            name=item.resource,
            write_disposition=PARTITION_REPLACE,
            merge_key=SOURCE_FILE,
        )
        for item in DATA_ITEMS
    ]


SPEC = SourceSpec("entsoe", entsoe_source, max_days_per_run=MAX_DAYS_PER_RUN)
