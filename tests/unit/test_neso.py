from datetime import date

from power_desk.ingest.sources import neso
from power_desk.ingest.windows import DateRange


def test_upload_query_selects_a_page_of_the_days_uploads_in_upload_order():
    sql = neso.upload_query(neso.DATASETS[0], DateRange(date(2024, 3, 1), date(2024, 3, 2)), offset=10_000)
    assert sql == (
        'select * from "9e539e05-e09c-4983-91fd-c766f03d0339" '
        "where \"Data Upload Time GMT\" >= '2024-03-01' and \"Data Upload Time GMT\" < '2024-03-03' "
        'order by "Data Upload Time GMT", _id limit 10000 offset 10000'
    )


def test_fetch_uploads_pages_until_a_short_page_and_drops_datastore_columns(monkeypatch):
    row = {"_full_text": "x", "Auction Type": "Day Ahead"}
    pages = [[{"_id": i, **row} for i in range(n)] for n in (neso.PAGE_ROWS, 2)]
    offsets = []

    def fetch_json(url, params):
        offsets.append(int(params["sql"].rsplit(" ", 1)[1]))
        return {"result": {"records": pages[len(offsets) - 1]}}

    monkeypatch.setattr(neso.http, "fetch_json", fetch_json)
    fetched = list(neso.fetch_uploads(neso.DATASETS[0], DateRange(date(2024, 3, 1), date(2024, 3, 1))))
    assert offsets == [0, neso.PAGE_ROWS]
    assert [len(page) for page in fetched] == [neso.PAGE_ROWS, 2]
    assert fetched[1] == [{"Auction Type": "Day Ahead"}] * 2
