"""ENTSO-E Energy Identification Codes (EIC): reference data for areas, parties and resources.

Published by the ENTSO-E Central Issuing Office, regenerated nightly
(https://www.entsoe.eu/data/energy-identification-codes-eic/):
- `entsoe_eic__codes`: every active EIC, including codes issued by Local Issuing Offices
  (CIO_extraction-all-eic-codes.csv, `;`-delimited)
- `entsoe_eic__functions`: EIC functions with definitions, per code type and market (eicFunctions.csv)
- `entsoe_eic__issuing_offices`: the Local Issuing Office list (HTML table); the first two
  characters of an EIC identify its issuing office

Snapshots, not streams: each resource re-reads the whole file and loads with dlt's `scd2`
merge strategy, so renamed, changed and withdrawn codes keep their history
(`_dlt_valid_from` / `_dlt_valid_to`). A file whose ETag / content is unchanged is skipped,
and a skipped run changes nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
import csv
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import io
import logging
from typing import Any

import dlt
from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltResource

from power_desk.ingest import http
from power_desk.ingest.spec import RunWindow, SourceSpec

logger = logging.getLogger(__name__)

BLOB = "https://eepublicdownloads.blob.core.windows.net/cio-lio/csv"
CODES_URL = f"{BLOB}/CIO_extraction-all-eic-codes.csv"
FUNCTIONS_URL = f"{BLOB}/eicFunctions.csv"
ISSUING_OFFICES_URL = "https://www.entsoe.eu/data/energy-identification-codes-eic/"
SCD2: TMergeDispositionDict = {"disposition": "merge", "strategy": "scd2"}


def parse_csv(text: str, delimiter: str) -> list[dict[str, str]]:
    """Rows of a published CSV, without the NUL bytes some extracts contain."""
    return list(csv.DictReader(io.StringIO(text.replace("\x00", "")), delimiter=delimiter))


class _IssuingOfficeTable(HTMLParser):
    """Rows of the `LIO Code | Name | Country | Website | EIC site | Email | Operates in` table."""

    LEADING_COLUMNS = 6  # LIO Code .. Email; the `Operates in` icons follow

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._in_cell = False
        self._cell_text: list[str] = []
        self._cells: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr" and (attributes.get("id") or "").isdigit():
            self._in_row, self._cells = True, []
        elif tag == "td" and self._in_row:
            self._in_cell, self._cell_text = True, []
            self._cells.append({"text": "", "href": None, "icons": []})
        elif self._in_cell and tag == "a" and attributes.get("href"):
            self._cells[-1]["href"] = attributes["href"]
        elif self._in_cell and tag == "i":
            self._cells[-1]["icons"].append(attributes.get("class") or "")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_cell:
            self._cells[-1]["text"] = "".join(self._cell_text).replace("​", "").strip()
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if len(self._cells) >= self.LEADING_COLUMNS:
                self.rows.append(self._issuing_office(self._cells))
            self._in_row = False

    def _issuing_office(self, cells: list[dict[str, Any]]) -> dict[str, Any]:
        code, name, country, website, eic_site, email = cells[: self.LEADING_COLUMNS]
        operates_in = " ".join(icon for cell in cells[self.LEADING_COLUMNS :] for icon in cell["icons"])
        return {
            "lio_code": code["text"],
            "name": name["text"],
            "country": country["text"],
            "website": website["href"],
            "eic_site": eic_site["href"],
            "email": (email["href"] or "").removeprefix("mailto:") or None,
            "electricity": "ee-icon-elec" in operates_in,
            "gas": "ee-icon-gas" in operates_in,
        }


def parse_issuing_offices(page_html: str) -> list[dict[str, Any]]:
    parser = _IssuingOfficeTable()
    parser.feed(page_html)
    if not parser.rows:
        raise ValueError("Local Issuing Office table not found on the EIC page")
    return parser.rows


@dataclass(frozen=True)
class Snapshot:
    resource: str
    url: str
    parse: Callable[[str], list[dict[str, Any]]]
    natural_key: tuple[str, ...]  # published column names


SNAPSHOTS = (
    Snapshot("entsoe_eic__codes", CODES_URL, lambda text: parse_csv(text, ";"), ("EicCode",)),
    Snapshot(
        "entsoe_eic__functions",
        FUNCTIONS_URL,
        lambda text: parse_csv(text, ","),
        ("EIC Function", "EIC Type", "Valid in Market"),
    ),
    Snapshot("entsoe_eic__issuing_offices", ISSUING_OFFICES_URL, parse_issuing_offices, ("lio_code",)),
)


def changed_rows(snapshot: Snapshot) -> Iterator[list[dict[str, Any]]]:
    """All rows of the published file, unless it is unchanged since its last load."""
    state = dlt.current.resource_state()
    previous = state.get("source_file", {})
    text, validators = http.fetch_if_changed(snapshot.url, etag=previous.get("etag") or None)
    digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else previous.get("sha256")
    new_text = text if digest != previous.get("sha256") else None
    state["source_file"] = {
        "url": snapshot.url,
        "etag": validators.get("etag") or previous.get("etag"),
        "last_modified": validators.get("last_modified") or previous.get("last_modified"),
        "sha256": digest,
        "changed": new_text is not None,
    }
    if new_text is not None:
        rows = snapshot.parse(new_text)
        logger.info("%s: %d rows from %s", snapshot.resource, len(rows), snapshot.url)
        yield rows


@dlt.source(name="entsoe_eic")
def entsoe_eic_source(window: RunWindow | None = None) -> list[DltResource]:
    """Snapshots ignore the run window of the shared source interface."""
    return [
        dlt.resource(
            changed_rows(snapshot),
            name=snapshot.resource,
            write_disposition=SCD2,
            primary_key=list(snapshot.natural_key),
            file_format="parquet",
        )
        for snapshot in SNAPSHOTS
    ]


SPEC = SourceSpec("entsoe_eic", entsoe_eic_source, max_days_per_run=1)
