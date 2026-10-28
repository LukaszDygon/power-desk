"""ENTSO-E Transparency Platform data items, as monthly file partitions of the File Library.

The File Library re-exports a month's file while its data changes. Each run lists a data item's
folder and loads the files new or changed since their last load (the publisher's
`lastUpdatedTimestamp`, kept in resource state), oldest month first, covering at most `max_days`
days of months; `capped` is recorded when more changed files remain. Bounded backfills
(`window.end`) load every file in range and leave the state untouched.

Rows are loaded as published: DuckDB's CSV reader infers their types and dlt names and hashes them.
Each table keeps versions (`scd2`) merged on its natural key, so a revision closes the row's previous
version; the same row may come from more than one file. The cursor is the latest `UpdateTime(UTC)`:
revisions and re-forecasts of earlier periods are new data.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, timedelta
import logging
from pathlib import Path
import tempfile

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.common.typing import TDataItems
from dlt.sources import DltResource
from dlt.sources.filesystem.helpers import fetch_json
import duckdb

from power_desk.ingest.sources.entsoe_file_library import ExportFile, FileLibraryClient
from power_desk.ingest.spec import RunWindow, SourceSpec
from power_desk.ingest.windows import DateRange, LastWindow

logger = logging.getLogger(__name__)

SCD2: TMergeDispositionDict = {"disposition": "merge", "strategy": "scd2"}
MAX_DAYS_PER_RUN = 186  # about six monthly files per data item and run
BATCH_ROWS = 50_000
UPDATE_TIME = "UpdateTime(UTC)"
AREA_KEY = ("DateTime(UTC)", "ResolutionCode", "AreaCode", "AreaTypeCode")


@dataclass(frozen=True)
class DataItem:
    resource: str
    folder: str  # <data item>_<Transparency Regulation article>_<release>
    natural_key: tuple[str, ...]  # published column names


DATA_ITEMS = (
    DataItem("entsoe__actual_total_load", "ActualTotalLoad_6.1.A_r3", AREA_KEY),
    DataItem("entsoe__day_ahead_total_load_forecast", "DayAheadTotalLoadForecast_6.1.B_r3", AREA_KEY),
    DataItem("entsoe__generation_per_type", "AggregatedGenerationPerType_16.1.B_C_r3", (*AREA_KEY, "ProductionType")),
    DataItem(
        "entsoe__wind_solar_forecast", "GenerationForecastsForWindAndSolar_14.1.D_r3", (*AREA_KEY, "ProductionType")
    ),
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


def file_partitions(client: FileLibraryClient, item: DataItem, window: RunWindow) -> Iterator[TDataItems]:
    state = {} if window.bounded else dlt.current.resource_state()
    loaded: dict[str, str] = state.setdefault("source_files", {})
    previous: LastWindow = state.get("last_window", {})
    plan = plan_files(client.list_folder(item.folder), loaded, window)
    cursor = previous.get("cursor_last_value")
    for file in plan.files:
        logger.info("%s: loading %s (%s bytes zipped)", item.resource, file.name, file.size)
        with tempfile.TemporaryDirectory() as tmp, duckdb.connect() as con:
            export = con.read_csv(str(client.download(item.folder, file.name, Path(tmp) / file.name)), sep="\t")
            cursor = latest_update(export, cursor)
            yield from fetch_json(export, BATCH_ROWS)
        loaded[file.name] = file.last_updated
    if not window.bounded:
        state["last_window"] = window_record(plan, cursor, previous)


def latest_update(export: duckdb.DuckDBPyRelation, cursor: str | None) -> str | None:
    [(latest,)] = export.aggregate(f'max("{UPDATE_TIME}")').fetchall()
    return max(filter(None, [cursor, latest.replace(tzinfo=UTC).isoformat() if latest else None]), default=None)


def window_record(plan: FilePlan, cursor: str | None, previous: LastWindow) -> LastWindow:
    """The run's `last_window`: months covered (else the previous run's), `capped`, and the latest update loaded."""
    record = LastWindow(capped=plan.capped, files_loaded=len(plan.files), cursor_last_value=cursor)
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
            write_disposition=SCD2,
            primary_key=list(item.natural_key),
            merge_key=list(item.natural_key),
            file_format="parquet",
        )
        for item in DATA_ITEMS
    ]


SPEC = SourceSpec("entsoe", entsoe_source, max_days_per_run=MAX_DAYS_PER_RUN)
