from datetime import date

from power_desk_elt.ingest.sources import neso
from power_desk_elt.ingest.windows import DateRange


def test_fetch_uploads_pages_until_a_short_page(monkeypatch):
    pages = [[{"_id": i, "Auction Type": "Day Ahead"} for i in range(n)] for n in (neso.PAGE_ROWS, 2)]
    requests = []

    def fetch_json(url, params):
        requests.append(params)
        return {"result": {"records": pages[len(requests) - 1]}}

    monkeypatch.setattr(neso.http, "fetch_json", fetch_json)
    fetched = list(neso.fetch_uploads(neso.DATASETS[0], DateRange(date(2024, 3, 1), date(2024, 3, 1))))
    assert fetched == pages
