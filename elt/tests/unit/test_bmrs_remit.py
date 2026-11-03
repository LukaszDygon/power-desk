from datetime import date

from power_desk_elt.ingest.sources import bmrs
from power_desk_elt.ingest.windows import DateRange


def test_remit_list_asks_for_every_revision_published_on_the_days():
    params = bmrs.remit_list_params(DateRange(date(2024, 3, 1), date(2024, 3, 7)))
    assert params == {"from": "2024-03-01T00:00:00Z", "to": "2024-03-07T23:59:59Z", "latestRevisionOnly": "false"}


def test_fetch_remit_fetches_the_listed_messages_by_id_in_batches(monkeypatch):
    listed = [{"id": i, "mrid": f"m{i % 7}"} for i in range(bmrs.REMIT_IDS_PER_REQUEST + 3, 0, -1)]
    requests = []

    def fetch_json(url, params):
        requests.append(url)
        if url == bmrs.REMIT_LIST_URL:
            return {"data": [*listed, listed[0]]}  # a message listed twice is fetched once
        return {"data": [{"id": i} for i in params["messageId"]]}

    monkeypatch.setattr(bmrs.http, "fetch_json", fetch_json)
    pages = list(bmrs.fetch_remit(DateRange(date(2024, 3, 1), date(2024, 3, 1))))
    assert requests == [bmrs.REMIT_LIST_URL, bmrs.REMIT_URL, bmrs.REMIT_URL]
    assert [len(page) for page in pages] == [bmrs.REMIT_IDS_PER_REQUEST, 3]
    assert [m["id"] for page in pages for m in page] == list(range(1, bmrs.REMIT_IDS_PER_REQUEST + 4))
