from concurrent.futures import Executor, Future
from datetime import UTC, date, datetime
import json

import pytest
import yaml

from power_desk_elt.ingest.seed import synthetic
from power_desk_elt.ingest.sources import desnz_repd, ecmwf
from power_desk_elt.ingest.windows import DateRange
from power_desk_elt.settings import ELT_ROOT


def test_dbt_selects_the_same_sites_as_the_ingest():
    variables = yaml.safe_load((ELT_ROOT / "dbt" / "dbt_project.yml").read_text())["vars"]
    assert variables["weather_site_status"] == ecmwf.SITE_STATUS
    assert set(variables["weather_site_technologies"]) == ecmwf.SITE_TECHNOLOGIES
    assert variables["weather_site_min_capacity_mw"] == ecmwf.SITE_MIN_CAPACITY_MW


IFS = ecmwf.DATASETS[0]
RUN = datetime(2024, 3, 1, 12, tzinfo=UTC)


def test_file_url_follows_the_portal_layout():
    assert IFS.file_url(RUN, 24, "index") == (
        "https://data.ecmwf.int/forecasts/20240301/12z/ifs/0p25/oper/20240301120000-24h-oper-fc.index"
    )


def test_ifs_runs_are_00z_and_12z_with_85_steps_to_360_hours():
    runs = list(ecmwf.run_times(IFS, DateRange(date(2024, 3, 1), date(2024, 3, 2))))
    assert [ecmwf.run_stamp(run) for run in runs] == ["2024030100", "2024030112", "2024030200", "2024030212"]
    assert len(IFS.steps[0]) == 85
    assert (IFS.steps[0][:2], IFS.steps[0][48:50], IFS.steps[0][-1]) == ((0, 3), (144, 150), 360)


AIFS = next(dataset for dataset in ecmwf.DATASETS if dataset.resource == "ecmwf__aifs_single")


def test_aifs_file_url_follows_the_portal_layout():
    # as listed on the portal on 2026-11-02
    assert AIFS.file_url(datetime(2026, 11, 2, 12, tzinfo=UTC), 24, "grib2") == (
        "https://data.ecmwf.int/forecasts/20261102/12z/aifs-single/0p25/oper/20261102120000-24h-oper-fc.grib2"
    )


def test_aifs_runs_every_6_hours_with_61_steps_to_360_hours():
    runs = list(ecmwf.run_times(AIFS, DateRange(date(2026, 11, 2), date(2026, 11, 2))))
    assert [ecmwf.run_stamp(run) for run in runs] == ["2026110200", "2026110206", "2026110212", "2026110218"]
    assert all(steps == tuple(range(0, 361, 6)) for steps in AIFS.steps.values())


def test_field_ranges_read_an_aifs_index():
    # lines of the AIFS Single 2026-11-02 12z step 24 index (`class` ai, `model` aifs-single)
    head = (
        '{"domain": "g", "date": "20261102", "time": "1200", "expver": "0001", "class": "ai", "type": "fc",'
        ' "stream": "oper"'
    )
    index = "\n".join(
        (
            head + ', "step": "24", "levelist": "50", "levtype": "pl", "param": "z", "model": "aifs-single",'
            ' "_offset": 0, "_length": 772388}',
            head + ', "levtype": "sfc", "step": "24", "param": "tp", "model": "aifs-single",'
            ' "_offset": 12935931, "_length": 364098}',
            head + ', "step": "24", "levtype": "sfc", "param": "2t", "model": "aifs-single",'
            ' "_offset": 55919092, "_length": 248836}',
        )
    )
    assert ecmwf.field_ranges(index) == [(12935931, 13300028), (55919092, 56167927)]


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


def repd_row(ref_id, technology, capacity, status="Operational", country="England", x="302219", y="166320"):
    return {
        "Ref ID": ref_id,
        "Technology Type": technology,
        "Installed Capacity (MWelec)": capacity,
        "Development Status (short)": status,
        "Country": country,
        "X-coordinate": x,
        "Y-coordinate": y,
    }


def test_select_sites_keeps_operational_wind_and_solar_of_at_least_50_mw_in_wgs84():
    sites = ecmwf.select_sites(
        [
            repd_row("1", "Wind Onshore", "50"),
            repd_row("2", "Wind Onshore", "60", country="Northern Ireland", x="117392", y="488885"),
            repd_row("3", "Solar Photovoltaics", "49.9"),
            repd_row("4", "Wind Offshore", "800", status="Under Construction"),
            repd_row("5", "Biomass (dedicated)", "100"),
            repd_row("6", "Wind Onshore", "60", x=""),
            repd_row("7", "Solar Photovoltaics", "n/a"),
        ]
    )
    assert [site["ref_id"] for site in sites] == ["1", "2"]
    assert sites[0]["latitude"] == pytest.approx(51.387, abs=0.001)  # Aberthaw, British National Grid
    assert sites[0]["longitude"] == pytest.approx(-3.407, abs=0.001)
    assert sites[1]["latitude"] == pytest.approx(54.218, abs=0.001)  # Newry: Northern Ireland is on it too
    assert sites[1]["longitude"] == pytest.approx(-6.337, abs=0.001)


def test_repd_extract_parses_cp1252_with_line_breaks_inside_quoted_fields():
    text = 'Ref ID,Site Name,Address\r\n1,Caf\xe9 Wind,"Unit 1\nHigh St"\r\n2,Moor,"Farm\rLane"\r\n'
    rows = desnz_repd.parse_extract(text.encode(desnz_repd.ENCODING).decode(desnz_repd.ENCODING))
    assert rows == [
        {"Ref ID": "1", "Site Name": "Café Wind", "Address": "Unit 1\nHigh St"},
        {"Ref ID": "2", "Site Name": "Moor", "Address": "Farm\rLane"},
    ]


def test_field_rows_hold_the_grib_keys_and_the_nearest_grid_point_value():
    index, content = synthetic.ecmwf_step_file("oper", RUN, 24)
    entries = {entry["param"]: entry for entry in map(json.loads, index.splitlines())}
    message = lambda param: content[entries[param]["_offset"] : entries[param]["_offset"] + entries[param]["_length"]]  # noqa: E731
    sites = [
        {"ref_id": "a", "latitude": 51.38, "longitude": -3.41},
        {"ref_id": "b", "latitude": 51.4, "longitude": -3.4},
    ]
    grids: dict = {}
    (row,) = ecmwf.field_rows(message("2t"), sites, grids)  # both sites share a grid point
    assert {k: row[k] for k in ("dataDate", "dataTime", "stepRange", "stepType", "shortName", "units")} == {
        "dataDate": 20240301,
        "dataTime": 1200,
        "stepRange": "24",
        "stepType": "instant",
        "shortName": "2t",
        "units": "K",
    }
    assert (row["latitude"], row["longitude"]) == (51.5, -3.5)
    row_index, column_index = int((61 - 51.5) / 0.25), int((-3.5 + 11) / 0.25)
    assert row["value"] == pytest.approx(synthetic._field_values("2t", RUN, 24)[row_index, column_index], abs=0.01)
    (accumulated,) = ecmwf.field_rows(message("ssrd"), sites, grids)
    assert (accumulated["stepType"], accumulated["stepRange"], accumulated["units"]) == ("accum", "0-24", "J m**-2")


def test_aifs_seed_files_carry_the_aifs_parameters_and_units():
    # AIFS Single publishes tcc as 228164 in % and tp as 228228 in kg m-2, where IFS has 164 (0 - 1) and 228 m
    sites = [{"ref_id": "a", "latitude": 51.4, "longitude": -3.4}]
    rows = {}
    for model in ("ifs", "aifs-single"):
        index, content = synthetic.ecmwf_step_file("oper", RUN, 24, model)
        for entry in map(json.loads, index.splitlines()):
            if entry["param"] in ("tcc", "tp"):
                message = content[entry["_offset"] : entry["_offset"] + entry["_length"]]
                (rows[model, entry["param"]],) = ecmwf.field_rows(message, sites, {})
    keys = lambda row: (row["shortName"], row["paramId"], row["units"], row["stepType"])  # noqa: E731
    assert keys(rows["ifs", "tcc"]) == ("tcc", 164, "(0 - 1)", "instant")
    assert keys(rows["ifs", "tp"]) == ("tp", 228, "m", "accum")
    assert keys(rows["aifs-single", "tcc"]) == ("tcc", 228164, "%", "instant")
    assert keys(rows["aifs-single", "tp"]) == ("tp", 228228, "kg m**-2", "accum")
    assert rows["aifs-single", "tcc"]["value"] == pytest.approx(100 * rows["ifs", "tcc"]["value"], rel=0.01)
    assert rows["aifs-single", "tp"]["value"] == pytest.approx(1000 * rows["ifs", "tp"]["value"], rel=0.01)
