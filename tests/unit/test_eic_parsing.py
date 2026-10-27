from power_desk.ingest.seed.replay import SEED_DIR
from power_desk.ingest.sources.entsoe_eic import parse_csv, parse_issuing_offices

PUBLISHED_ROWS = """
<table><tr id="10"><td>10</td><td>ENTSO-E</td><td>EU</td>
<td>&#8203; <a href="https://www.entsoe.eu/"><i class="ee-icon-globe"></i></a></td>
<td><a href="http://www.eiccodes.eu/"><i></i></a></td><td><a href="mailto:cio-admin@entsoe.eu"><i></i></a></td>
<td><i class="ee-icon-elec"></i></td><td></td></tr>
<tr id="56"><td>56</td><td>GASTSO</td><td>UA</td><td><a href="https://tsoua.com/"></a></td><td></td><td></td><td></td>
<td><i class="ee-icon-gas"></i></td></tr></table>
"""


def test_parse_issuing_offices_reads_links_and_market_icons():
    first, second = parse_issuing_offices(PUBLISHED_ROWS)
    assert first == {
        "lio_code": "10",
        "name": "ENTSO-E",
        "country": "EU",
        "website": "https://www.entsoe.eu/",
        "eic_site": "http://www.eiccodes.eu/",
        "email": "cio-admin@entsoe.eu",
        "electricity": True,
        "gas": False,
    }
    assert (second["electricity"], second["gas"], second["email"]) == (False, True, None)


def test_parse_issuing_offices_reads_the_recorded_seed_page():
    rows = parse_issuing_offices((SEED_DIR / "entsoe_eic" / "eic-issuing-offices.html").read_text(encoding="utf-8"))
    assert rows and all(len(row["lio_code"]) == 2 for row in rows)


def test_parse_csv_strips_nul_bytes():
    [row] = parse_csv("EicCode;EicLongName\n10YGB----------A;Great\x00 Britain\n", ";")
    assert row == {"EicCode": "10YGB----------A", "EicLongName": "Great Britain"}
