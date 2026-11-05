"""DESNZ Renewable Energy Planning Database (REPD): renewable electricity projects through planning.

DESNZ publishes a quarterly extract on GOV.UK
(https://www.gov.uk/government/publications/renewable-energy-planning-database-quarterly-extract):
one row per project (`Ref ID`), with its technology, installed capacity, development status and
location (`X-coordinate` / `Y-coordinate`: British National Grid, Northern Ireland included). The
column definitions are on the Excel release's Definition Sheet. The extract's address changes with
each release, so a run looks up the current CSV attachment through the GOV.UK Content API first.

A snapshot, not a stream (`ingest/snapshot.py`): `desnz_repd__repd` re-reads the whole extract and loads
with dlt's `scd2` merge strategy, so projects that change status or leave the extract keep their history
(`_dlt_valid_from` / `_dlt_valid_to`). An unchanged extract is skipped. The file is Windows-1252
encoded, with mixed line endings inside quoted fields.
"""

from __future__ import annotations

import csv
import io

import dlt
from dlt.sources import DltResource

from power_desk_elt.ingest import http
from power_desk_elt.ingest.snapshot import Snapshot, snapshot_resource
from power_desk_elt.ingest.spec import RunWindow, SourceSpec

CONTENT_URL = (
    "https://www.gov.uk/api/content/government/publications/renewable-energy-planning-database-quarterly-extract"
)


def current_extract_url() -> str:
    """The CSV attachment of the publication's current release."""
    attachments = http.fetch_json(CONTENT_URL)["details"]["attachments"]
    return next(item["url"] for item in attachments if item.get("content_type") == "text/csv")


def parse_extract(text: str) -> list[dict[str, str]]:
    """Rows of the extract as published (`newline=""` keeps line breaks inside quoted fields)."""
    return list(csv.DictReader(io.StringIO(text, newline="")))


REPD = Snapshot("desnz_repd__repd", current_extract_url, parse_extract, ("Ref ID",), encoding="cp1252")


@dlt.source(name="desnz_repd")
def desnz_repd_source(window: RunWindow | None = None) -> list[DltResource]:
    """Snapshots ignore the run window of the shared source interface."""
    return [snapshot_resource(REPD)]


SPEC = SourceSpec("desnz_repd", desnz_repd_source)
