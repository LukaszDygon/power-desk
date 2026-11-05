"""ENTSO-E Energy Identification Codes (EIC): reference data for areas, parties and resources.

Published by the ENTSO-E Central Issuing Office, regenerated nightly
(https://www.entsoe.eu/data/energy-identification-codes-eic/):
- `entsoe_eic__codes`: every active EIC, including codes issued by Local Issuing Offices
  (CIO_extraction-all-eic-codes.csv, `;`-delimited)
- `entsoe_eic__functions`: EIC functions with definitions, per code type and market (eicFunctions.csv)
- `entsoe_eic__issuing_offices`: the Local Issuing Office list (an HTML table, read by `IssuingOffice`);
  the first two characters of an EIC identify its issuing office

Snapshots, not streams (`ingest/snapshot.py`): each resource re-reads the whole file and loads it as
scd2 versions, so renamed, changed and withdrawn codes keep their history; an unchanged file is skipped.
"""

from __future__ import annotations

import csv
from html.parser import HTMLParser
import io
from typing import Any

import dlt
from dlt.sources import DltResource
from pydantic import BaseModel, ConfigDict, Field

from power_desk_elt.ingest.snapshot import Snapshot, snapshot_resource
from power_desk_elt.ingest.spec import RunWindow, SourceSpec

BLOB = "https://eepublicdownloads.blob.core.windows.net/cio-lio/csv"
CODES_URL = f"{BLOB}/CIO_extraction-all-eic-codes.csv"
FUNCTIONS_URL = f"{BLOB}/eicFunctions.csv"
ISSUING_OFFICES_URL = "https://www.entsoe.eu/data/energy-identification-codes-eic/"
ZERO_WIDTH_SPACE = chr(0x200B)  # the page's padding in table cells


def parse_csv(text: str, delimiter: str) -> list[dict[str, str]]:
    """Rows of a published CSV, as published."""
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


class HtmlTable(HTMLParser):
    """The header and rows of a page's first table with a header row, each cell as published.

    A cell holds its link's address, else the icons it shows (their class names) and its text,
    space-separated (the page pads cells with zero-width spaces); a header spanning several columns, or
    the last one, holds the values of all its cells.
    """

    def __init__(self) -> None:
        super().__init__()
        self.header: list[tuple[str, int]] = []  # (text, columns spanned)
        self.rows: list[list[str | None]] = []
        self._cell: dict[str, Any] | None = None
        self._row: list[str | None] | None = None
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self._done:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._cell = {"tag": tag, "span": int(attributes.get("colspan") or 1), "href": None, "parts": []}
        elif self._cell is not None and tag == "a" and attributes.get("href"):
            self._cell["href"] = attributes["href"]
        elif self._cell is not None and tag == "i" and attributes.get("class"):
            self._cell["parts"].append(attributes["class"])

    def handle_data(self, data: str) -> None:
        if self._cell is not None and (text := data.replace(ZERO_WIDTH_SPACE, "").strip()):
            self._cell["parts"].append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if tag in ("th", "td") and self._cell is not None and self._row is not None:
            cell, self._cell = self._cell, None
            if cell["tag"] == "th":
                self.header.append((" ".join(cell["parts"]), cell["span"]))
            else:
                self._row.append(cell["href"] or " ".join(cell["parts"]) or None)
        elif tag == "tr" and self._row is not None:
            row, self._row = self._row, None
            if row and self.header:
                self.rows.append(row)
        elif tag == "table" and self.header:
            self._done = True

    def records(self) -> list[dict[str, str | None]]:
        """Each row by header text."""
        records = []
        for row in self.rows:
            record, position = {}, 0
            for n, (name, span) in enumerate(self.header):
                cells = row[position:] if n == len(self.header) - 1 else row[position : position + span]
                record[name] = " ".join(cell for cell in cells if cell) or None
                position += span
            records.append(record)
        return records


class IssuingOffice(BaseModel):
    """A row of the Local Issuing Office table on the EIC page, by the table's header text as published."""

    model_config = ConfigDict(extra="allow", frozen=True)

    lio_code: str = Field(alias="LIO Code")
    name: str = Field(alias="Name")
    country: str | None = Field(alias="Country")
    website: str | None = Field(alias="Website")  # the link's address
    eic_site: str | None = Field(alias="EIC site")
    email: str | None = Field(alias="Email")  # a `mailto:` link
    operates_in: str | None = Field(alias="Operates in")  # sector icons (`ee-icon-elec`, ...) and notes

    @classmethod
    def parse(cls, page_html: str) -> list[dict[str, Any]]:
        """The table's rows, keyed by its header text."""
        table = HtmlTable()
        table.feed(page_html)
        if not table.rows:
            raise ValueError("Local Issuing Office table not found on the EIC page")
        return [cls.model_validate(record).model_dump(by_alias=True) for record in table.records()]


SNAPSHOTS = (
    Snapshot("entsoe_eic__codes", CODES_URL, lambda text: parse_csv(text, ";"), ("EicCode",)),
    Snapshot(
        "entsoe_eic__functions",
        FUNCTIONS_URL,
        lambda text: parse_csv(text, ","),
        ("EIC Function", "EIC Type", "Valid in Market"),
    ),
    Snapshot("entsoe_eic__issuing_offices", ISSUING_OFFICES_URL, IssuingOffice.parse, ("LIO Code",)),
)


@dlt.source(name="entsoe_eic")
def entsoe_eic_source(window: RunWindow | None = None) -> list[DltResource]:
    """Snapshots ignore the run window of the shared source interface."""
    return [snapshot_resource(snapshot) for snapshot in SNAPSHOTS]


SPEC = SourceSpec("entsoe_eic", entsoe_eic_source)
