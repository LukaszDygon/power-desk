"""DESNZ Renewable Energy Planning Database (REPD): renewable electricity projects through planning.

DESNZ publishes a quarterly extract on GOV.UK
(https://www.gov.uk/government/publications/renewable-energy-planning-database-quarterly-extract):
one row per project (`Ref ID`), with its technology, installed capacity, development status and
location (`X-coordinate` / `Y-coordinate`: British National Grid, Northern Ireland included). The
column definitions are on the Excel release's Definition Sheet. The extract's address changes with
each release, so a run looks up the current CSV attachment through the GOV.UK Content API first.

A snapshot, not a stream: `desnz_repd__repd` re-reads the whole extract and loads with dlt's `scd2`
merge strategy, so projects that change status or leave the extract keep their history
(`_dlt_valid_from` / `_dlt_valid_to`). An unchanged extract is skipped. The file is Windows-1252
encoded, with mixed line endings inside quoted fields.
"""

from __future__ import annotations

from collections.abc import Iterator
import csv
import io
from typing import Any

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltResource

from power_desk_elt.ingest import http
from power_desk_elt.ingest.snapshot import Snapshot, changed_rows
from power_desk_elt.ingest.spec import RunWindow, SourceSpec

CONTENT_URL = (
    "https://www.gov.uk/api/content/government/publications/renewable-energy-planning-database-quarterly-extract"
)
RESOURCE = "desnz_repd__repd"
NATURAL_KEY = ("Ref ID",)
ENCODING = "cp1252"
SCD2: TMergeDispositionDict = {"disposition": "merge", "strategy": "scd2"}


def current_extract_url() -> str:
    """The CSV attachment of the publication's current release."""
    attachments = http.fetch_json(CONTENT_URL)["details"]["attachments"]
    return next(item["url"] for item in attachments if item.get("content_type") == "text/csv")


def parse_extract(text: str) -> list[dict[str, str]]:
    """Rows of the extract as published (`newline=""` keeps line breaks inside quoted fields)."""
    return list(csv.DictReader(io.StringIO(text, newline="")))


def extract_rows() -> Iterator[list[dict[str, Any]]]:
    yield from changed_rows(Snapshot(RESOURCE, current_extract_url(), parse_extract, NATURAL_KEY, ENCODING))


@dlt.source(name="desnz_repd")
def desnz_repd_source(window: RunWindow | None = None) -> list[DltResource]:
    """Snapshots ignore the run window of the shared source interface."""
    return [
        dlt.resource(
            extract_rows(),
            name=RESOURCE,
            write_disposition=SCD2,
            primary_key=list(NATURAL_KEY),
            file_format="parquet",
        )
    ]


SPEC = SourceSpec("desnz_repd", desnz_repd_source, max_days_per_run=1)
