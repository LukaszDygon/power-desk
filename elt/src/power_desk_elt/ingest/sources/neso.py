"""NESO Data Portal: NESO's net transfer capacity restrictions per GB interconnector, as streams.

Each interconnector's dataset has one resource of current values: a row per auction (`Auction Type`)
and hourly operational period, holding NESO's submission and its `Data Upload Time GMT`. NESO usually
replaces a resubmitted row, but at times appends it as a further row with a later upload time. Rows
are read from the portal's CKAN datastore by upload time (the incremental cursor), a page at a time:
a resubmission is new data. Each table keeps the versions of its rows (`scd2`) merged on the natural
key; the upload time joins the primary key only, so a resubmission closes every earlier version of
its key, rows not uploaded again stay current, and staging keeps the latest upload. Upload times are
GMT, so requested date ranges need no padding.

Rows are loaded as published, the datastore's own columns (`_id`, `_full_text`) included.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import count
import logging
from typing import Any

import dlt
from dlt.sources import DltResource

from power_desk_elt.ingest import http
from power_desk_elt.ingest.spec import SCD2, RunWindow, SourceSpec
from power_desk_elt.ingest.windows import DateRange, day_after, incremental_window

logger = logging.getLogger(__name__)

SQL_URL = "https://api.neso.energy/api/3/action/datastore_search_sql"
MAX_DAYS_PER_RUN = 186
DAYS_PER_REQUEST = 31
PAGE_ROWS = 10_000
UPLOAD_TIME = "Data Upload Time GMT"
NATURAL_KEY = ["Auction Type", "Operational Period Start Date and Time GMT"]  # the merge key


@dataclass(frozen=True)
class Dataset:
    resource: str
    package: str  # NESO Data Portal dataset name
    resource_id: str  # its datastore resource of current values (the archived ones are not loaded)


DATASETS = (
    Dataset("neso__ifa_ntc", "ifa", "9e539e05-e09c-4983-91fd-c766f03d0339"),
    Dataset("neso__ifa2_ntc", "ifa2", "f9ff9381-6eb1-40cd-903b-ca7282b9f2a9"),
    Dataset("neso__eleclink_ntc", "eleclink", "1f748d48-1daf-4f1a-a5f1-d581e86a2190"),
    Dataset("neso__nemolink_ntc", "nemolink", "7d43e2a0-1c22-4e05-895d-756bae210756"),
    Dataset("neso__nsl_ntc", "nsl", "9db51c01-922d-413d-8b67-3938fdc14bdb"),
    Dataset("neso__viking_ntc", "viking", "f4ee9a34-1bb5-405e-b4a0-bacb193fb188"),
)


def upload_query(dataset: Dataset, days: DateRange, offset: int) -> str:
    """One page of the rows uploaded from `days.first` 00:00 to before `days.last + 1` 00:00 GMT."""
    return (
        f'select * from "{dataset.resource_id}" '
        f"where \"{UPLOAD_TIME}\" >= '{days.first.isoformat()}' and \"{UPLOAD_TIME}\" < '{day_after(days.last)}' "
        f'order by "{UPLOAD_TIME}", _id limit {PAGE_ROWS} offset {offset}'
    )


def fetch_uploads(dataset: Dataset, days: DateRange) -> Iterator[list[dict[str, Any]]]:
    """Rows uploaded on `days`, in pages."""
    logger.info("%s: %s..%s", dataset.resource, days.first, days.last)
    for offset in count(0, PAGE_ROWS):
        payload = http.fetch_json(SQL_URL, params={"sql": upload_query(dataset, days, offset)})
        rows = payload["result"]["records"]
        if rows:
            yield rows
        if len(rows) < PAGE_ROWS:
            return


def stream(dataset: Dataset, window: RunWindow) -> DltResource:
    initial_value = window.start.isoformat()
    end_value = day_after(window.end) if window.end else None

    @dlt.resource(
        name=dataset.resource,
        write_disposition=SCD2,
        primary_key=[*NATURAL_KEY, UPLOAD_TIME],
        merge_key=NATURAL_KEY,
        file_format="parquet",
    )
    def rows(
        cursor: dlt.sources.incremental[str] = dlt.sources.incremental(
            f"'{UPLOAD_TIME}'", initial_value=initial_value, end_value=end_value
        ),
    ) -> Iterator[list[dict[str, Any]]]:
        for days in incremental_window(cursor, window.max_days).chunks(DAYS_PER_REQUEST):
            yield from fetch_uploads(dataset, days)

    return rows


@dlt.source(name="neso")
def neso_source(window: RunWindow) -> list[DltResource]:
    return [stream(dataset, window) for dataset in DATASETS]


SPEC = SourceSpec("neso", neso_source, max_days_per_run=MAX_DAYS_PER_RUN)
