"""ENTSO-E Transparency Platform data items, as monthly file partitions of the File Library.

The File Library re-exports a month's file daily while its data changes. Each run lists a data
item's folder and loads the files new or changed since their last load (the publisher's
`lastUpdatedTimestamp`, kept in resource state), oldest month first, covering at most
`max_days` days of months; `capped` is recorded when more changed files remain. A loaded
file replaces every row previously loaded from it (`merge_key` `_source_file`), so revisions and
withdrawals follow the publication. Bounded backfills (`window.end`) load every file in range and
leave the state untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import logging

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltResource
import pyarrow as pa
import pyarrow.compute as pc

from power_desk.ingest.sources.entsoe_file_library import (
    SOURCE_FILE,
    ExportFile,
    FileLibraryClient,
    column_name,
    parse_export,
)
from power_desk.ingest.spec import RunWindow, SourceSpec
from power_desk.ingest.windows import DateRange, LastWindow

logger = logging.getLogger(__name__)

PARTITION_REPLACE: TMergeDispositionDict = {"disposition": "merge", "strategy": "delete-insert"}
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


@dataclass(frozen=True)
class FilePlan:
    """The files a run loads, oldest month first; `capped` when more changed files remain."""

    files: list[ExportFile]
    capped: bool = False

    @property
    def months(self) -> DateRange | None:
        """The months the files cover."""
        return DateRange(self.files[0].month.first, self.files[-1].month.last) if self.files else None


def plan_files(files: list[ExportFile], loaded: dict[str, str], window: RunWindow) -> FilePlan:
    """Bounded backfills load every file in range; open-ended runs the changed ones, up to `max_days` of months."""
    requested = DateRange(window.start, window.end or date.max)
    in_range = sorted((file for file in files if file.month.overlaps(requested)), key=lambda file: file.month.first)
    if window.bounded:
        return FilePlan(in_range)
    changed = [file for file in in_range if loaded.get(file.name) != file.last_updated]
    if not changed:
        return FilePlan([])
    limit = changed[0].month.first + timedelta(days=max(window.max_days, 1))
    batch = [file for file in changed if file.month.first < limit]
    return FilePlan(batch, capped=len(batch) < len(changed))


def latest_mtu(table: pa.Table, cursor: str | None) -> str | None:
    latest = pc.max(table[MTU_START]).as_py()  # pyright: ignore[reportAttributeAccessIssue]  # generated at import
    return max(filter(None, [cursor, latest.isoformat() if latest else None]), default=None)


def file_partitions(client: FileLibraryClient, item: DataItem, window: RunWindow) -> Iterator[pa.Table]:
    state = {} if window.bounded else dlt.current.resource_state()
    loaded: dict[str, str] = state.setdefault("source_files", {})
    previous: LastWindow = state.get("last_window", {})
    plan = plan_files(client.list_folder(item.folder), loaded, window)
    cursor = previous.get("cursor_last_value")
    for file in plan.files:
        logger.info("%s: loading %s (%s bytes zipped)", item.resource, file.name, file.size)
        table = parse_export(client.download(item.folder, file.name), file.name)
        if table.num_rows:
            cursor = latest_mtu(table, cursor)
            yield table
        loaded[file.name] = file.last_updated
    if not window.bounded:
        state["last_window"] = window_record(plan, cursor, previous)


def window_record(plan: FilePlan, cursor: str | None, previous: LastWindow) -> LastWindow:
    """The run's `last_window`: months covered (else the previous run's), `capped`, and the latest MTU loaded."""
    record = LastWindow(
        capped=plan.capped,
        files_loaded=len(plan.files),
        checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
        cursor_last_value=cursor,
    )
    if months := plan.months:
        record["first_day"], record["last_day"] = months.first.isoformat(), months.last.isoformat()
    elif "first_day" in previous and "last_day" in previous:
        record["first_day"], record["last_day"] = previous["first_day"], previous["last_day"]
    return record


@dlt.source(name="entsoe")
def entsoe_source(window: RunWindow) -> list[DltResource]:
    client = FileLibraryClient()
    return [
        dlt.resource(
            file_partitions(client, item, window),
            name=item.resource,
            write_disposition=PARTITION_REPLACE,
            merge_key=SOURCE_FILE,
        )
        for item in DATA_ITEMS
    ]


SPEC = SourceSpec("entsoe", entsoe_source, max_days_per_run=MAX_DAYS_PER_RUN)
