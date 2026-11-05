from concurrent.futures import Executor, Future
from datetime import UTC, datetime
import json

import pytest

from power_desk_elt.ingest.seed import synthetic
from power_desk_elt.ingest.sources import desnz_repd, ecmwf

RUN = datetime(2024, 3, 1, 12, tzinfo=UTC)


def test_field_ranges_keep_the_surface_fields_read_in_byte_order():
    index = "\n".join(
        json.dumps(entry)
        for entry in (
            {"param": "2t", "levtype": "sfc", "_offset": 500, "_length": 100},
            {"param": "t", "levtype": "pl", "levelist": "850", "_offset": 0, "_length": 500},
            {"param": "msl", "levtype": "sfc", "_offset": 600, "_length": 50},
            {"param": "100u", "levtype": "sfc", "_offset": 650, "_length": 10},
        )
    )
    assert ecmwf.field_ranges(index) == [(500, 599), (650, 659)]


def test_a_file_not_published_yet_or_any_more_is_none_and_other_errors_raise(monkeypatch):
    import requests

    from power_desk_elt.ingest import http

    def get(status):
        response = requests.Response()
        response.status_code, response.url = status, "https://data.ecmwf.int/x.index"

        def raising_get(*args, **kwargs):  # dlt's client raises on 4xx / 5xx itself
            raise requests.HTTPError(response=response)

        return raising_get

    monkeypatch.setattr(http.requests, "get", get(404))
    assert http.fetch_bytes("https://data.ecmwf.int/x.index") is None
    monkeypatch.setattr(http.requests, "get", get(403))
    with pytest.raises(requests.HTTPError):
        http.fetch_bytes("https://data.ecmwf.int/x.index")


def test_steps_are_fetched_in_order_with_at_most_the_worker_count_in_flight():
    submitted, done = [], []

    def fetch(step):
        assert len(submitted) - len(done) <= ecmwf.FETCH_WORKERS
        done.append(step)
        return step

    class Deferred(Future):  # runs a step when its result is asked for, so submissions show what is in flight
        def __init__(self, run):
            super().__init__()
            self.run = run

        def result(self, timeout=None):
            return self.run()

    class Pool(Executor):
        def submit(self, fn, /, *args, **kwargs):
            submitted.append(args[0])
            return Deferred(lambda: fn(*args, **kwargs))

    assert list(ecmwf.fetched_in_order(Pool(), fetch, range(20))) == list(range(20))
    assert len(submitted) == 20


def test_repd_extract_parses_cp1252_with_line_breaks_inside_quoted_fields():
    text = 'Ref ID,Site Name,Address\r\n1,Caf\xe9 Wind,"Unit 1\nHigh St"\r\n2,Moor,"Farm\rLane"\r\n'
    rows = desnz_repd.parse_extract(text.encode(desnz_repd.REPD.encoding).decode(desnz_repd.REPD.encoding))
    assert rows == [
        {"Ref ID": "1", "Site Name": "Café Wind", "Address": "Unit 1\nHigh St"},
        {"Ref ID": "2", "Site Name": "Moor", "Address": "Farm\rLane"},
    ]


def test_a_grib_message_parses_to_its_keys_and_the_value_at_the_grid_point_nearest_each_point():
    index, content = synthetic.ecmwf_step_file("oper", RUN, 24)
    entry = next(entry for entry in map(json.loads, index.splitlines()) if entry["param"] == "ssrd")
    message = content[entry["_offset"] : entry["_offset"] + entry["_length"]]
    (row,) = ecmwf.GridValue.parse(message, [(51.38, -3.41), (51.4, -3.4)], {})  # both share a grid point
    assert {k: row[k] for k in ("dataDate", "dataTime", "stepRange", "stepType", "shortName", "units")} == {
        "dataDate": 20240301,
        "dataTime": 1200,
        "stepRange": "0-24",
        "stepType": "accum",
        "shortName": "ssrd",
        "units": "J m**-2",
    }
    assert (row["latitude"], row["longitude"]) == (51.5, -3.5)
    row_index, column_index = int((61 - 51.5) / 0.25), int((-3.5 + 11) / 0.25)
    assert row["value"] == pytest.approx(synthetic._field_values("ssrd", RUN, 24)[row_index, column_index], rel=0.01)
