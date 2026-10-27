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
from dlt.sources import DltResource

from power_desk.ingest import http
from power_desk.ingest.spec import SourceSpec

logger = logging.getLogger(__name__)

BLOB = "https://eepublicdownloads.blob.core.windows.net/cio-lio/csv"
CODES_URL = f"{BLOB}/CIO_extraction-all-eic-codes.csv"
FUNCTIONS_URL = f"{BLOB}/eicFunctions.csv"
ISSUING_OFFICES_URL = "https://www.entsoe.eu/data/energy-identification-codes-eic/"
SCD2 = {"disposition": "merge", "strategy": "scd2"}


def parse_csv(text: str, delimiter: str) -> list[dict[str, str]]:
    """Rows of a published CSV, without the NUL bytes some extracts contain."""
    return list(csv.DictReader(io.StringIO(text.replace("\x00", "")), delimiter=delimiter))


class _IssuingOfficeTable(HTMLParser):
    """Rows of the `LIO Code | Name | Country | Website | EIC site | Email | Operates in` table."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self._cell: list[str] = []
        self._cells: list[dict[str, Any]] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "tr" and (a.get("id") or "").isdigit():
            self._row, self._cells = {}, []
        elif tag == "td" and self._row is not None:
            self._in_cell, self._cell = True, []
            self._cells.append({"text": "", "href": None, "icons": []})
        elif self._in_cell and tag == "a" and a.get("href"):
            self._cells[-1]["href"] = a["href"]
        elif self._in_cell and tag == "i":
            self._cells[-1]["icons"].append(a.get("class") or "")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_cell:
            self._cells[-1]["text"] = "".join(self._cell).replace("​", "").strip()
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            c = self._cells
            if len(c) >= 6:
                icons = " ".join(i for cell in c[6:] for i in cell["icons"])
                self.rows.append(
                    {
                        "lio_code": c[0]["text"],
                        "name": c[1]["text"],
                        "country": c[2]["text"],
                        "website": c[3]["href"],
                        "eic_site": c[4]["href"],
                        "email": (c[5]["href"] or "").removeprefix("mailto:") or None,
                        "electricity": "ee-icon-elec" in icons,
                        "gas": "ee-icon-gas" in icons,
                    }
                )
            self._row = None


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


SNAPSHOTS = (
    Snapshot("entsoe_eic__codes", CODES_URL, lambda text: parse_csv(text, ";")),
    Snapshot("entsoe_eic__functions", FUNCTIONS_URL, lambda text: parse_csv(text, ",")),
    Snapshot("entsoe_eic__issuing_offices", ISSUING_OFFICES_URL, parse_issuing_offices),
)


def changed_rows(snapshot: Snapshot) -> Iterator[list[dict[str, Any]]]:
    """All rows of the published file, unless it is unchanged since its last load."""
    state = dlt.current.resource_state()
    previous = state.get("source_file", {})
    text, validators = http.fetch_if_changed(snapshot.url, etag=previous.get("etag") or None)
    digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else previous.get("sha256")
    changed = text is not None and digest != previous.get("sha256")
    state["source_file"] = {
        "url": snapshot.url,
        **previous,
        **{k: v for k, v in validators.items() if v},
        "sha256": digest,
        "changed": changed,
    }
    if changed:
        rows = snapshot.parse(text)
        logger.info("%s: %d rows from %s", snapshot.resource, len(rows), snapshot.url)
        yield rows


@dlt.source(name="entsoe_eic")
def entsoe_eic_source(
    initial_date: str | None = None, end_date: str | None = None, max_days_per_run: int | None = None
) -> list[DltResource]:
    """Snapshots ignore the date arguments of the shared source interface."""
    return [
        dlt.resource(changed_rows(snapshot), name=snapshot.resource, write_disposition=SCD2) for snapshot in SNAPSHOTS
    ]


SPEC = SourceSpec("entsoe_eic", entsoe_eic_source, max_days_per_run=1)
