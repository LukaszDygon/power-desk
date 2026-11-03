"""dbt over the seed week: marts populated across sources, load-id scoped rebuilds, guards and completeness."""

from __future__ import annotations

from datetime import datetime

from power_desk_elt.ingest.pipeline import make_pipeline, make_source, run
from power_desk_elt.ingest.registry import SOURCES
from power_desk_elt.ingest.seed.load import load_seed
from power_desk_elt.ingest.seed.replay import SeedPublishers, replay
from power_desk_elt.transform.dbt import run_dbt
from power_desk_elt.transform.loads import pending_load_ids, tracked_models
import power_desk_warehouse as warehouse
from tests.support import build, query

GB_MARTS = {"mart_gb_generation_mix", "mart_gb_demand_vs_forecast", "mart_gb_hourly_summary"}
SEED_AREAS = 11


def test_seed_build_populates_every_mart_and_processes_every_load(seeded_warehouse):
    assert query(seeded_warehouse, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
    audited = query(
        seeded_warehouse, "select count(distinct load_id), count(distinct model_name) from dlt_meta.dlt_load_audit"
    )
    assert audited == [(query(seeded_warehouse, "select count(*) from raw._dlt_loads")[0][0], len(tracked_models()))]
    assert set(tracked_models()) > GB_MARTS
    # 7 days x 288 five-minute intervals, x 48 settlement periods, x 24 hours
    assert [query(seeded_warehouse, f"select count(*) from marts.{m}")[0][0] for m in sorted(GB_MARTS)] == [
        336,
        2016,
        168,
    ]


def test_combined_marts_hold_every_source_and_area(seeded_warehouse):
    sources = (
        "select string_agg(distinct source_dataset, ',' order by source_dataset), count(distinct area_eic_code) "
        "from marts.{}"
    )
    assert query(seeded_warehouse, sources.format("mart_generation_actual")) == [
        ("ENTSOE_16.1.B_C,FUELINST,PVLIVE", SEED_AREAS + 1)
    ]
    assert query(seeded_warehouse, sources.format("mart_demand_actual"))[0][0] == "ENTSOE_6.1.A,INDO"
    assert query(seeded_warehouse, sources.format("mart_demand_forecast"))[0][0] == "ENTSOE_6.1.B,NDF"
    assert query(seeded_warehouse, sources.format("mart_generation_forecast"))[0][0] == "ENTSOE_14.1.D,WINDFOR"
    capacities = "select string_agg(distinct source_dataset, ',' order by source_dataset) from marts.{}"
    assert query(seeded_warehouse, capacities.format("mart_transfer_capacity")) == [
        ("ENTSOE_11.1.A,NESO_ELECLINK,NESO_IFA,NESO_IFA2,NESO_NEMOLINK,NESO_NSL,NESO_VIKING",)
    ]
    assert query(
        seeded_warehouse, "select count(*) from marts.mart_generation_actual where technology_code is null"
    ) == [(0,)]


def test_a_revised_load_rebuilds_only_the_grains_it_touches(warehouse_copy, tmp_path):
    before = dict(
        query(
            warehouse_copy,
            "select settlement_period, _dbt_invocation_id from marts.mart_gb_demand_vs_forecast "
            "where settlement_date = '2024-03-03'",
        )
    )
    publishers = SeedPublishers.from_seed()
    publishers.records["INDO"] = [
        {**r, "publishTime": "2024-03-08T12:00:00Z", "demand": 99_999}
        for r in publishers.records["INDO"]
        if r["settlementDate"] == "2024-03-03" and r["settlementPeriod"] in (10, 11)
    ]
    with replay(publishers):
        info = run(
            make_pipeline("bmrs", warehouse_copy),
            make_source("bmrs", SOURCES["bmrs"].window("2024-03-08", "2024-03-08"), ["bmrs__indo"]),
        )
    assert pending_load_ids(warehouse_copy) == list(info.loads_ids)
    assert build(warehouse_copy, tmp_path) == 0

    after = dict(
        query(
            warehouse_copy,
            "select settlement_period, _dbt_invocation_id from marts.mart_gb_demand_vs_forecast "
            "where settlement_date = '2024-03-03'",
        )
    )
    assert {p for p in after if after[p] != before[p]} == {10, 11}
    assert query(
        warehouse_copy,
        "select actual_demand_mw from marts.mart_gb_demand_vs_forecast "
        "where settlement_date = '2024-03-03' and settlement_period = 10",
    ) == [(99_999,)]
    assert pending_load_ids(warehouse_copy) == []


def test_a_neso_resubmission_replaces_the_restriction_in_the_entity(warehouse_copy, tmp_path):
    publishers = SeedPublishers.from_seed()
    [original] = [
        r
        for r in publishers.records["neso__nsl_ntc"]
        if r["Auction Type"] == "Day Ahead" and r["Operational Period Start Date and Time GMT"] == "2024-03-04T18:00:00"
    ]
    publishers.records["neso__nsl_ntc"] = [
        {**original, "Data Upload Time GMT": "2024-03-08T12:00:00", "Flow in MW From GB": 1}
    ]
    with replay(publishers):
        run(
            make_pipeline("neso", warehouse_copy),
            make_source("neso", SOURCES["neso"].window("2024-03-08", "2024-03-08"), ["neso__nsl_ntc"]),
        )
    assert build(warehouse_copy, tmp_path) == 0
    assert query(
        warehouse_copy,
        "select out_area_map_code, transfer_capacity_mw from ods.ods_transfer_capacity o "
        "join (select area_eic_code, display_name as out_area_map_code from dims.dim_area where is_current) a "
        "on a.area_eic_code = o.out_area_eic_code "
        "where source_dataset = 'NESO_NSL' and source_code = 'Day Ahead' and timestamp_utc = '2024-03-04 18:00' "
        "order by all",
    ) == [("GB", 1.0), ("NO2", float(original["Flow in MW To GB"]))]


def test_overlapping_periods_resolve_to_the_most_recently_published_in_the_hourly_mart(warehouse_copy, tmp_path):
    # a pending load republishes FR (60-minute in the seed) at 15 minutes for one hour, published later, and NL
    # (15-minute) at 60 minutes for another, published earlier: the entity keeps every row, the hourly mart
    # takes the most recent publication, and incremental builds match full ones
    with warehouse.connect(warehouse_copy, read_only=False) as con:
        con.execute(
            "insert into raw._dlt_loads (load_id, schema_name, status, inserted_at) "
            "values ('1999999999.2', 'manual', 0, now())"
        )
        con.execute("""insert into raw.entsoe__actual_total_load
                       select r.* replace (r.date_time_utcx + to_minutes(t.m * 15) as date_time_utcx,
                                           'PT15M' as resolution_code, 1000.0 + t.m as total_load_mwx,
                                           r.update_time_utcx + interval 1 day as update_time_utcx,
                                           '1999999999.2' as _dlt_load_id, 'fr15-' || t.m as _dlt_id)
                       from raw.entsoe__actual_total_load r, range(4) t(m)
                       where area_code = '10YFR-RTE------C' and _dlt_valid_to is null
                         and date_time_utcx = timestamptz '2024-03-04 10:00:00+00'""")
        con.execute("""insert into raw.entsoe__actual_total_load
                       select * replace ('PT60M' as resolution_code, 99999.0 as total_load_mwx,
                                         update_time_utcx - interval 1 day as update_time_utcx,
                                         '1999999999.2' as _dlt_load_id, 'nl60' as _dlt_id)
                       from raw.entsoe__actual_total_load
                       where area_code = '10YNL----------L' and _dlt_valid_to is null
                         and date_time_utcx = timestamptz '2024-03-04 12:00:00+00'""")
    assert build(warehouse_copy, tmp_path) == 0

    published = (
        "select interval_minutes, count(*), avg(demand_mw) from ods.ods_demand_actual where area_eic_code = '{0}' "
        "and timestamp_utc >= timestamp '{1}' and timestamp_utc < timestamp '{1}' + interval 1 hour group by all "
        "order by all"
    )
    assert query(warehouse_copy, published.format("10YFR-RTE------C", "2024-03-04 10:00"))[0] == (15, 4, 1001.5)
    [nl_15, nl_60] = query(warehouse_copy, published.format("10YNL----------L", "2024-03-04 12:00"))
    assert nl_15[:2] == (15, 4) and nl_60 == (60, 1, 99999.0)

    hourly = (
        "select demand_mw, coverage from marts.mart_demand_actual where area_eic_code = '{0}' "
        "and timestamp_utc = timestamp '{1}'"
    )
    assert query(warehouse_copy, hourly.format("10YFR-RTE------C", "2024-03-04 10:00")) == [(1001.5, 1.0)]
    assert query(warehouse_copy, hourly.format("10YNL----------L", "2024-03-04 12:00")) == [(round(nl_15[2], 3), 1.0)]

    for relation in ("ods.ods_demand_actual", "marts.mart_demand_actual"):
        rows = f"select * from {relation} order by all"
        incremental = query(warehouse_copy, rows)
        full_refresh = ["run", "--select", relation.split(".")[1], "--full-refresh"]
        assert run_dbt(full_refresh, warehouse_copy, target_path=tmp_path / "target") == 0
        assert query(warehouse_copy, rows) == incremental


def test_a_calendar_day_ends_where_the_next_begins_across_a_clock_change(warehouse_copy, tmp_path):
    # Brussels-midnight days around the clock changes of 31 March 2024 (a 23-hour day in UTC) and 27 October
    # 2024 (25 hours), arriving one load at a time, each published after the next: every hour holds exactly
    # one day's value, and the incremental builds match a full build
    days = [
        ("2024-03-29 23:00", 101.0),
        ("2024-03-30 23:00", 102.0),
        ("2024-03-31 22:00", 103.0),
        ("2024-10-25 22:00", 201.0),
        ("2024-10-26 22:00", 202.0),
        ("2024-10-27 23:00", 203.0),
    ]
    for i, (start, mw) in enumerate(days):
        load_id = f"199999999{i}.5"
        with warehouse.connect(warehouse_copy, read_only=False) as con:
            con.execute(
                "insert into raw._dlt_loads (load_id, schema_name, status, inserted_at) "
                f"values ('{load_id}', 'manual', 0, now())"
            )
            con.execute(f"""insert into raw.entsoe__forecasted_transfer_capacities
                            select * replace (timestamptz '{start}:00+00' as date_time_utcx,
                                              {mw} as forecast_transfer_capacity_mwx,
                                              timestamptz '2024-11-30 00:00:00+00' - to_days({i}) as update_time_utcx,
                                              '{load_id}' as _dlt_load_id, 'dst-{i}' as _dlt_id)
                            from raw.entsoe__forecasted_transfer_capacities
                            where contract_type = 'Month-ahead' and out_area_map_code = 'GB'
                              and in_area_map_code = 'FR' and _dlt_valid_to is null
                            limit 1""")
        assert build(warehouse_copy, tmp_path) == 0

    hours = (
        "select transfer_capacity_mw, count(*), min(coverage), max(coverage) from marts.mart_transfer_capacity "
        "where source_code = 'Month-ahead' and out_area_eic_code = '10YGB----------A' "
        "and in_area_eic_code = '10YFR-RTE------C' and timestamp_utc >= timestamp '2024-03-29 23:00' "
        "group by all order by all"
    )
    assert query(warehouse_copy, hours) == [
        (101.0, 24, 1.0, 1.0),
        (102.0, 23, 1.0, 1.0),
        (103.0, 24, 1.0, 1.0),
        (201.0, 24, 1.0, 1.0),
        (202.0, 25, 1.0, 1.0),
        (203.0, 24, 1.0, 1.0),
    ]

    rows = "select * from marts.mart_transfer_capacity order by all"
    incremental = query(warehouse_copy, rows)
    full_refresh = ["run", "--select", "mart_transfer_capacity", "--full-refresh"]
    assert run_dbt(full_refresh, warehouse_copy, target_path=tmp_path / "target") == 0
    assert query(warehouse_copy, rows) == incremental


def test_hourly_marts_weight_by_minutes_and_record_coverage(seeded_warehouse):
    # FUELINST is published every 5 minutes: an hour of it is the mean of its twelve values
    [(expected, slots)] = query(
        seeded_warehouse,
        "select round(avg(generation_mw), 3), count(*) from ods.ods_generation_actual "
        "where source_dataset = 'FUELINST' and source_code = 'CCGT' "
        "and timestamp_utc >= timestamp '2024-03-04 10:00' and timestamp_utc < timestamp '2024-03-04 11:00'",
    )
    assert slots == 12
    assert query(
        seeded_warehouse,
        "select generation_mw, coverage from marts.mart_generation_actual where source_dataset = 'FUELINST' "
        "and source_code = 'CCGT' and timestamp_utc = timestamp '2024-03-04 10:00'",
    ) == [(expected, 1.0)]
    # a year-ahead capacity (a month-long period) holds in every hour of its month
    assert query(
        seeded_warehouse,
        "select count(*), min(coverage), count(distinct transfer_capacity_mw) from marts.mart_transfer_capacity "
        "where time_horizon = 'year_ahead' and source_dataset = 'ENTSOE_11.1.A' "
        "and out_area_eic_code = '10YGB----------A' and in_area_eic_code = '10YFR-RTE------C'",
    ) == [(30 * 24, 1.0, 1)]


def test_a_duplicated_raw_row_fails_its_guard_and_keeps_the_load_pending(warehouse_copy, tmp_path):
    with warehouse.connect(warehouse_copy, read_only=False) as con:
        con.execute(
            "insert into raw._dlt_loads (load_id, schema_name, status, inserted_at) "
            "values ('1999999999.1', 'manual', 0, now())"
        )
        con.execute("""insert into raw.bmrs__indo
                       select * replace ('1999999999.1' as _dlt_load_id, 'dup' as _dlt_id, demand + 1 as demand)
                       from raw.bmrs__indo where settlement_date = '2024-03-05' and settlement_period = 20""")
    assert build(warehouse_copy, tmp_path) != 0
    assert query(
        warehouse_copy,
        "select settlement_date, settlement_period, n_rows from test_failures.bmrs__indo_unique_natural_key",
    ) == [("2024-03-05", 20, 2)]
    audited = {
        r[0]
        for r in query(warehouse_copy, "select model_name from dlt_meta.dlt_load_audit where load_id = '1999999999.1'")
    }
    assert "mart_gb_demand_vs_forecast" not in audited
    assert "1999999999.1" in pending_load_ids(warehouse_copy)


def test_completeness_flags_a_missing_settlement_period(warehouse_copy, tmp_path):
    with warehouse.connect(warehouse_copy, read_only=False) as con:
        con.execute("delete from raw.bmrs__indo where settlement_date = '2024-03-04' and settlement_period = 17")
    assert (
        run_dbt(
            ["test", "--select", "stg_bmrs__indo", "--vars", '{"dlt_scope": "all"}'],
            warehouse_copy,
            target_path=tmp_path / "target",
        )
        != 0
    )
    assert query(
        warehouse_copy,
        "select settlement_date::text, settlement_period from test_failures.stg_bmrs__indo_no_missing_periods",
    ) == [("2024-03-04", 17)]


def test_scoped_tests_read_only_rows_of_pending_loads(seeded_warehouse, tmp_path):
    assert (
        run_dbt(
            ["compile", "--select", "ods_demand_actual", "--vars", '{"dlt_load_ids": ["L1"]}'],
            seeded_warehouse,
            target_path=tmp_path / "target",
        )
        == 0
    )
    compiled = next(
        (tmp_path / "target" / "compiled").rglob("not_null_ods_demand_actual_interval_minutes.sql")
    ).read_text()
    assert "_dlt_load_id in (select unnest(cast(['L1'] as varchar[])) as load_id)" in compiled


def test_a_first_build_by_hand_processes_every_load(tmp_path, monkeypatch):
    monkeypatch.setenv("POWER_DESK_PIPELINES_DIR", str(tmp_path / "pipelines"))  # no state from other tests' loads
    db = tmp_path / "fresh.duckdb"
    load_seed(db)
    assert run_dbt(["build"], db, target_path=tmp_path / "target") == 0
    assert query(db, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]


def remit_mrid(number: int, sender: str = "NGET") -> str:
    return f"48X000000000SEED-{sender}-RMT-{number:08d}"


DIDCOT, DRAX, WALNEY, PEMBROKE = remit_mrid(1), remit_mrid(2), remit_mrid(5), remit_mrid(7)
EVENT_HOURS = (
    "select min(timestamp_utc), max(timestamp_utc), count(distinct timestamp_utc) "
    "from marts.mart_unavailability where mrid = '{}'"
)


def test_remit_marts_place_each_events_latest_revision_on_the_hour(seeded_warehouse):
    # revision 2 shortened Didcot's outage to 2024-03-04 20:00: only its hours remain
    assert query(seeded_warehouse, EVENT_HOURS.format(DIDCOT)) == [
        (datetime(2024, 3, 3, 6), datetime(2024, 3, 4, 19), 38)
    ]
    # Drax's outage profile: available capacity per interval, the event's unavailable capacity throughout
    drax = (
        "select timestamp_utc, available_capacity_mw, unavailable_capacity_mw, coverage from marts.mart_unavailability "
        f"where mrid = '{DRAX}' and timestamp_utc in ('2024-03-02 19:00', '2024-03-02 20:00') order by 1"
    )
    assert query(seeded_warehouse, drax) == [
        (datetime(2024, 3, 2, 19), 400.0, 265.0, 1.0),
        (datetime(2024, 3, 2, 20), 500.0, 265.0, 1.0),
    ]
    # one message listing two units: a series per unit; an open-ended event is not placed
    units = f"select count(distinct source_code) from marts.mart_unavailability where mrid = '{WALNEY}'"
    assert query(seeded_warehouse, units) == [(2,)]
    assert query(seeded_warehouse, EVENT_HOURS.format(remit_mrid(4)))[0][2] == 0
    # the dismissed nuclear outage stays in the combined mart, but not in the GB total
    statuses = "select distinct event_status from marts.mart_unavailability where mrid = '{}'"
    assert query(seeded_warehouse, statuses.format(remit_mrid(6))) == [("Dismissed",)]
    gb = (
        "select technology_code, unavailability_type, unavailable_capacity_mw, events "
        "from marts.mart_gb_generation_unavailability where timestamp_utc = '{}' order by 1"
    )
    assert query(seeded_warehouse, gb.format("2024-03-06 12:00")) == []
    assert query(seeded_warehouse, gb.format("2024-03-05 08:00")) == [("gas", "Planned", 225.0, 1)]
    # the transmission unavailability (Moyle) is not generation
    moyle = "select count(*) from marts.mart_gb_generation_unavailability where timestamp_utc = '2024-03-06 19:00'"
    assert query(seeded_warehouse, moyle) == [(0,)]


def test_a_remit_revision_rebuilds_every_hour_of_its_event(warehouse_copy, tmp_path):
    pembroke = f"select distinct _dbt_invocation_id from marts.mart_unavailability where mrid = '{PEMBROKE}'"
    untouched = query(warehouse_copy, pembroke)
    publishers = SeedPublishers.from_seed()
    messages = sorted(publishers.records["REMIT"], key=lambda m: m["id"])
    latest = {m["mrid"]: m for m in messages}
    revised = {"publishTime": "2024-03-08T12:00:00Z"}
    # Didcot shortened again, Walney's two units dismissed, Drax made open-ended
    didcot = {**latest[DIDCOT], **revised, "id": 201, "revisionNumber": 3, "eventEndTime": "2024-03-04T06:00:00Z"}
    walney = [
        {**m, **revised, "id": 202 + i, "revisionNumber": 2, "eventStatus": "Dismissed"}
        for i, m in enumerate(m for m in messages if m["mrid"] == WALNEY)
    ]
    drax = {k: v for k, v in latest[DRAX].items() if k not in ("eventEndTime", "outageProfile")}
    publishers.records["REMIT"] = [didcot, *walney, {**drax, **revised, "id": 204, "revisionNumber": 2}]
    with replay(publishers):
        run(
            make_pipeline("bmrs", warehouse_copy),
            make_source("bmrs", SOURCES["bmrs"].window("2024-03-08", "2024-03-08"), ["bmrs__remit"]),
        )
    assert build(warehouse_copy, tmp_path) == 0

    assert query(warehouse_copy, EVENT_HOURS.format(DIDCOT)) == [(datetime(2024, 3, 3, 6), datetime(2024, 3, 4, 5), 24)]
    assert query(warehouse_copy, EVENT_HOURS.format(DRAX))[0][2] == 0
    statuses = f"select distinct event_status from marts.mart_unavailability where mrid = '{WALNEY}'"
    assert query(warehouse_copy, statuses) == [("Dismissed",)]
    # the hours the revisions moved the events out of are gone from the GB total as well
    gb = "select technology_code from marts.mart_gb_generation_unavailability where timestamp_utc = '{}'"
    assert query(warehouse_copy, gb.format("2024-03-04 10:00")) == []
    assert query(warehouse_copy, gb.format("2024-03-02 16:00")) == []
    # every revision stays in the entity; events no load touched are not rebuilt
    revisions = f"select count(distinct revision_number) from ods.ods_unavailability where mrid = '{DIDCOT}'"
    assert query(warehouse_copy, revisions) == [(3,)]
    assert query(warehouse_copy, pembroke) == untouched


def test_a_nonconforming_area_code_resolves_to_its_registered_area(seeded_warehouse):
    # Elexon's 10YGB----------B (seed nonconforming_eic_codes) on the Moyle message: GB, rolled up through it
    resolved = (
        "select distinct a.registered_area_eic_code, a.display_name, a.is_bidding_zone, c.issuing_office_code "
        "from ods.ods_unavailability o join dims.dim_area a on a.area_eic_code = o.area_eic_code and a.is_current "
        "join dims.dim_eic_code c on c.eic_code = a.area_eic_code and c.valid_from = a.valid_from "
        "where o.area_eic_code = '10YGB----------B'"
    )
    assert query(seeded_warehouse, resolved) == [("10YGB----------A", "GB", True, None)]
    ancestors = (
        "select ancestor_area_eic_code, depth from dims.bridge_area_hierarchy "
        "where area_eic_code = '10YGB----------B' order by depth"
    )
    assert query(seeded_warehouse, ancestors) == [
        ("10YGB----------B", 0),
        ("10YGB----------A", 1),
        ("10Y1001A1001A92E", 2),
    ]
