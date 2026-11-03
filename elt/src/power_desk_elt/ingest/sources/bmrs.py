"""Elexon Insights Solution (BMRS) datasets, as streams, plus the BM unit reference list.

Each dataset is fetched one day per request from its incremental cursor: the publish time
(`publishTime`), or for datasets without one (MID) the interval start (`startTime`); records are
stored as published and merged on their natural key. A failed request fails the run, so the cursor
never moves past a gap. Settlement dates are UK-local, so requested date ranges are padded by a day.

REMIT messages (`bmrs__remit`) are listed by publish time (every revision, 7 days per request) and
fetched by Elexon's message id in batches: only that route carries the id, the one key unique per
published message (Elexon republishes some revisions, and one message may list several units).
Messages are immutable, a revision being a new message, so raw keeps every message (`scd2` merged on
the id) and a replayed window changes nothing; staging picks each event's latest revision. Their
outage profiles load as dlt's child table `bmrs__remit__outage_profile`.

The BM unit list (`bmrs__bmunits`) is a snapshot (`ingest/snapshot.py`): Elexon publishes no
validators, so the whole list is re-read on each run and skipped while its content is unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import batched
import json
import logging
from typing import Any

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltResource

from power_desk_elt.ingest import http
from power_desk_elt.ingest.snapshot import SCD2, Snapshot, snapshot_resource
from power_desk_elt.ingest.spec import RunWindow, SourceSpec
from power_desk_elt.ingest.windows import DateRange, day_after, incremental_window

logger = logging.getLogger(__name__)

API_ROOT = "https://data.elexon.co.uk/bmrs/api/v1"
API_BASE = f"{API_ROOT}/datasets"
REMIT_LIST_URL = f"{API_ROOT}/remit/list/by-publish"
REMIT_URL = f"{API_ROOT}/remit"
BMUNITS_URL = f"{API_ROOT}/reference/bmunits/all"
# one row per primary key: dlt drops repeats within a load (Elexon republishes some records verbatim)
DELETE_INSERT: TMergeDispositionDict = {"disposition": "merge", "strategy": "delete-insert"}
MAX_DAYS_PER_RUN = 7
REMIT_DAYS_PER_REQUEST = 7  # the publisher's limit for listing by publish time
REMIT_IDS_PER_REQUEST = 250
REMIT_KEY = "id"  # Elexon's message id


@dataclass(frozen=True)
class Dataset:
    resource: str
    code: str  # Elexon dataset code
    primary_key: tuple[str, ...]
    cursor: str = "publishTime"
    time_filter: tuple[str, str] = ("publishDateTimeFrom", "publishDateTimeTo")  # query parameters on `cursor`


DATASETS = (
    Dataset("bmrs__fuelinst", "FUELINST", ("settlementDate", "settlementPeriod", "fuelType", "startTime")),
    Dataset("bmrs__indo", "INDO", ("settlementDate", "settlementPeriod")),
    Dataset("bmrs__itsdo", "ITSDO", ("settlementDate", "settlementPeriod")),
    Dataset("bmrs__ndf", "NDF", ("settlementDate", "settlementPeriod", "publishTime")),
    Dataset("bmrs__windfor", "WINDFOR", ("startTime", "publishTime")),
    Dataset(
        "bmrs__mid",
        "MID",
        ("settlementDate", "settlementPeriod", "dataProvider"),
        cursor="startTime",
        time_filter=("from", "to"),
    ),
)


def fetch_records(dataset: Dataset, days: DateRange) -> list[dict[str, Any]]:
    """Records whose cursor is from `days.first` 00:00 to `days.last` 23:59:59 UTC."""
    logger.info("%s: %s..%s", dataset.resource, days.first, days.last)
    time_from, time_to = dataset.time_filter
    payload = http.fetch_json(
        f"{API_BASE}/{dataset.code}",
        params={
            time_from: f"{days.first.isoformat()}T00:00:00Z",
            time_to: f"{days.last.isoformat()}T23:59:59Z",
        },
    )
    return payload.get("data", []) if isinstance(payload, dict) else payload


def stream(dataset: Dataset, window: RunWindow) -> DltResource:
    initial_value = window.start.isoformat()
    end_value = day_after(window.end) if window.end else None

    @dlt.resource(
        name=dataset.resource,
        write_disposition=DELETE_INSERT,
        primary_key=list(dataset.primary_key),
        file_format="parquet",
    )
    def records(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            dataset.cursor, initial_value=initial_value, end_value=end_value
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for day in incremental_window(cursor, window.max_days).chunks(days=1):
            if rows := fetch_records(dataset, day):
                yield rows

    return records


def remit_list_params(days: DateRange) -> dict[str, str]:
    """Every revision published from `days.first` 00:00 to `days.last` 23:59:59 UTC."""
    return {
        "from": f"{days.first.isoformat()}T00:00:00Z",
        "to": f"{days.last.isoformat()}T23:59:59Z",
        "latestRevisionOnly": "false",
    }


def fetch_remit(days: DateRange) -> Iterator[list[dict[str, Any]]]:
    """REMIT messages published on `days`, by message id, a batch per request."""
    logger.info("bmrs__remit: %s..%s", days.first, days.last)
    listed = http.fetch_json(REMIT_LIST_URL, params=remit_list_params(days))["data"]
    for ids in batched(sorted({message[REMIT_KEY] for message in listed}), REMIT_IDS_PER_REQUEST, strict=False):
        yield http.fetch_json(REMIT_URL, params={"messageId": list(ids)})["data"]


def remit(window: RunWindow) -> DltResource:
    initial_value = window.start.isoformat()
    end_value = day_after(window.end) if window.end else None

    @dlt.resource(
        name="bmrs__remit",
        write_disposition=SCD2,
        primary_key=REMIT_KEY,
        merge_key=REMIT_KEY,
        file_format="parquet",
    )
    def messages(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            "publishTime", initial_value=initial_value, end_value=end_value
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for days in incremental_window(cursor, window.max_days).chunks(REMIT_DAYS_PER_REQUEST):
            yield from fetch_remit(days)

    return messages


# no key is documented, and the list repeats a unit under two EICs (WLNYO-4): versions by row hash only
BMUNITS = Snapshot("bmrs__bmunits", BMUNITS_URL, json.loads, natural_key=())


@dlt.source(name="bmrs")
def bmrs_source(window: RunWindow) -> list[DltResource]:
    return [*(stream(dataset, window) for dataset in DATASETS), remit(window), snapshot_resource(BMUNITS)]


SPEC = SourceSpec("bmrs", bmrs_source, max_days_per_run=MAX_DAYS_PER_RUN, window_padding_days=1)
