"""Snapshot (reference data) sources: parsing, unchanged-file skips and scd2 history."""

from __future__ import annotations

import duckdb
import pytest

from power_desk.ingest import common
from power_desk.ingest.entsoe_eic import parse_csv, parse_issuing_offices
from power_desk.ingest.pipelines import make_pipeline, make_source

ISSUING_OFFICES_PAGE = """
<table><tr><th>LIO Code</th><th>Name</th><th>Country</th><th>Website</th><th>EIC site</th><th>Email</th><th colspan="2">Operates in</th></tr>
<tr id="10"><td>10</td><td>ENTSO-E</td><td>EU</td><td>&#8203; <a href="https://www.entsoe.eu/"><i class="ee-icon-globe"></i></a></td>
<td><a href="http://www.eiccodes.eu/"><i class="ee-icon-globe2"></i></a></td><td><a href="mailto:cio-admin@entsoe.eu"><i></i></a></td>
<td><i class="ee-icon-elec"></i></td><td></td><td></td></tr>
<tr id="56"><td>56</td><td>GASTSO</td><td>UA</td><td><a href="https://tsoua.com/"></a></td><td></td><td></td><td></td>
<td><i class="ee-icon-gas"></i></td><td></td></tr>
</table>
"""

CODES_HEADER = "EicCode;EicDisplayName;EicLongName;EicParent;EicResponsibleParty;EicStatus;" \
               "MarketParticipantPostalCode;MarketParticipantIsoCountryCode;MarketParticipantVatCode;EicTypeFunctionList;type"


def codes_csv(*rows: str) -> str:
    return "\n".join([CODES_HEADER, *rows]) + "\n"


def test_parse_issuing_offices():
    rows = parse_issuing_offices(ISSUING_OFFICES_PAGE)
    assert [r["lio_code"] for r in rows] == ["10", "56"]
    assert rows[0] == {"lio_code": "10", "name": "ENTSO-E", "country": "EU", "website": "https://www.entsoe.eu/",
                      "eic_site": "http://www.eiccodes.eu/", "email": "cio-admin@entsoe.eu",
                      "electricity": True, "gas": False}
    assert (rows[1]["electricity"], rows[1]["gas"], rows[1]["email"]) == (False, True, None)


def test_parse_csv_strips_nul_bytes():
    rows = parse_csv(codes_csv("10YGB----------A;GB;Great\x00 Britain;;;Active;;GB;;Bidding Zone,Control Area;Y"), ";")
    assert rows[0]["EicLongName"] == "Great Britain"
    assert rows[0]["EicTypeFunctionList"] == "Bidding Zone,Control Area"


@pytest.fixture
def published(monkeypatch):
    """A fake publisher: `files[url]` is served with an ETag until changed; 304 when unchanged."""
    files: dict[str, str] = {}

    def fetch_if_changed(url, etag=None, timeout=120):
        text = files.get(url, "")
        tag = str(hash(text))
        return (None, {"etag": tag}) if etag == tag else (text, {"etag": tag})

    monkeypatch.setattr(common, "fetch_if_changed", fetch_if_changed)
    return files


def test_snapshot_keeps_history_and_skips_unchanged_files(published, tmp_path):
    from power_desk.ingest import entsoe_eic

    db = tmp_path / "w.duckdb"
    pipeline = make_pipeline("entsoe_eic", db_path=db, export_schema=False)

    def run():
        pipeline.run(make_source("entsoe_eic", resources=["raw_eic_codes"]))
        con = duckdb.connect(str(db), read_only=True)
        rows = con.execute("select eic_code, eic_display_name, _dlt_valid_to is null from raw.raw_eic_codes "
                           "order by eic_code, _dlt_valid_from").fetchall()
        con.close()
        return rows

    published[entsoe_eic.CODES_URL] = codes_csv("10YAA----------1;AA;Area A;;;Active;;;;Bidding Zone;Y",
                                                "10YBB----------2;BB;Area B;;;Active;;;;Control Area;Y")
    assert run() == [("10YAA----------1", "AA", True), ("10YBB----------2", "BB", True)]
    assert run() == [("10YAA----------1", "AA", True), ("10YBB----------2", "BB", True)]  # unchanged: skipped

    # A renamed, B withdrawn: old versions are closed, not deleted
    published[entsoe_eic.CODES_URL] = codes_csv("10YAA----------1;AA2;Area A;;;Active;;;;Bidding Zone;Y")
    assert run() == [("10YAA----------1", "AA", False), ("10YAA----------1", "AA2", True), ("10YBB----------2", "BB", False)]
