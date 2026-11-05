"""dbt over the seed week: marts populated across sources, load-id scoped rebuilds, guards and completeness."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from power_desk_elt.ingest.pipeline import make_pipeline, make_source, run
from power_desk_elt.ingest.registry import SOURCES
from power_desk_elt.ingest.seed.load import load_seed
from power_desk_elt.ingest.seed.replay import SeedPublishers, replay
from power_desk_elt.transform.dbt import run_dbt
from power_desk_elt.transform.loads import pending_load_ids, tracked_models
import power_desk_warehouse as warehouse
from tests.support import build, query

Records = dict[str, list[dict[str, Any]]]
REPUBLISHED = "2024-03-08T12:00:00Z"
DIDCOT = "48X000000000SEED-NGET-RMT-00000001"


def test_seed_build_populates_every_mart_and_processes_every_load(seeded_warehouse):
    assert query(seeded_warehouse, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
    audited = query(
        seeded_warehouse, "select count(distinct load_id), count(distinct model_name) from dlt_meta.dlt_load_audit"
    )
    assert audited == [(query(seeded_warehouse, "select count(*) from raw._dlt_loads")[0][0], len(tracked_models()))]
    marts = query(seeded_warehouse, "select table_name from information_schema.tables where table_schema = 'marts'")
    assert [m for (m,) in marts if query(seeded_warehouse, f"select count(*) from marts.{m}") == [(0,)]] == []


@pytest.mark.parametrize(
    ("mart", "sources"),
    [
        ("mart_generation_actual", "ENTSOE_16.1.B_C,FUELINST,PVLIVE"),
        ("mart_generation_forecast", "ENTSOE_14.1.D,WINDFOR"),
        ("mart_demand_actual", "ENTSOE_6.1.A,INDO"),
        ("mart_demand_forecast", "ENTSOE_6.1.B,NDF"),
        ("mart_energy_price", "ENTSOE_12.1.D,MID"),
        ("mart_transfer_capacity", "ENTSOE_11.1.A,NESO_ELECLINK,NESO_IFA,NESO_IFA2,NESO_NEMOLINK,NESO_NSL,NESO_VIKING"),
        ("mart_weather_forecast", "ECMWF_AIFS_SINGLE,ECMWF_IFS_OPER"),
    ],
)
def test_each_mart_holds_every_source_of_its_entity(seeded_warehouse, mart, sources):
    sql = f"select string_agg(distinct source_dataset, ',' order by source_dataset) from marts.{mart}"
    assert query(seeded_warehouse, sql) == [(sources,)]


def revise_indo(records: Records) -> list[tuple]:
    records["INDO"] = [
        {**r, "publishTime": REPUBLISHED, "demand": 99_999}
        for r in records["INDO"]
        if r["settlementDate"] == "2024-03-03" and r["settlementPeriod"] in (10, 11)
    ]
    return [([99_999.0],)]


def revise_neso(records: Records) -> list[tuple]:
    [original] = [
        r
        for r in records["neso__nsl_ntc"]
        if r["Auction Type"] == "Day Ahead" and r["Operational Period Start Date and Time GMT"] == "2024-03-04T18:00:00"
    ]
    records["neso__nsl_ntc"] = [{**original, "Data Upload Time GMT": "2024-03-08T12:00:00", "Flow in MW From GB": 1}]
    # out of GB (the restriction from GB), then into GB
    return [([1.0, float(original["Flow in MW To GB"])],)]


def revise_remit(records: Records) -> list[tuple]:
    latest = {m["mrid"]: m for m in sorted(records["REMIT"], key=lambda m: m["id"])}
    revision = {"publishTime": REPUBLISHED, "id": 201, "revisionNumber": 3, "eventEndTime": "2024-03-04T06:00:00Z"}
    records["REMIT"] = [{**latest[DIDCOT], **revision}]
    # the new revision is the latest; every earlier one is kept
    return [(datetime(2024, 3, 4, 6), 3)]


@pytest.mark.parametrize(
    ("source", "table", "revise", "entity_sql", "mart_sql", "mart_hours"),
    [
        pytest.param(
            "bmrs",
            "bmrs__indo",
            revise_indo,
            "select list(demand_mw) from ods.ods_demand_actual "
            "where source_dataset = 'INDO' and settlement_date = '2024-03-03' and settlement_period = 10",
            "select distinct timestamp_utc from marts.mart_demand_actual where source_dataset = 'INDO'",
            [datetime(2024, 3, 3, 4), datetime(2024, 3, 3, 5)],
            id="elexon-republication",
        ),
        pytest.param(
            "neso",
            "neso__nsl_ntc",
            revise_neso,
            "select list(transfer_capacity_mw order by out_area_eic_code) from ods.ods_transfer_capacity "
            "where source_dataset = 'NESO_NSL' and source_code = 'Day Ahead' and timestamp_utc = '2024-03-04 18:00'",
            "select distinct timestamp_utc from marts.mart_transfer_capacity where source_dataset = 'NESO_NSL'",
            [datetime(2024, 3, 4, 18)],
            id="neso-resubmission",
        ),
        pytest.param(
            "bmrs",
            "bmrs__remit",
            revise_remit,
            "select max(timestamp_utc + to_minutes(interval_minutes)) filter (where is_latest_revision), "
            f"count(distinct revision_number) from ods.ods_unavailability where mrid = '{DIDCOT}'",
            None,
            None,
            id="remit-revision",
        ),
    ],
)
def test_a_republished_row_replaces_the_earlier_one_and_rebuilds_only_what_it_touches(
    warehouse_copy, tmp_path, source, table, revise: Callable[[Records], list[tuple]], entity_sql, mart_sql, mart_hours
):
    publishers = SeedPublishers.from_seed()
    expected = revise(publishers.records)
    with replay(publishers):
        info = run(
            make_pipeline(source, warehouse_copy),
            make_source(source, SOURCES[source].window("2024-03-08", "2024-03-08"), [table]),
        )
    assert build(warehouse_copy, tmp_path) == 0
    assert query(warehouse_copy, entity_sql) == expected
    if mart_sql:
        loads = ", ".join(f"'{load_id}'" for load_id in info.loads_ids)
        rebuilt = query(warehouse_copy, f"{mart_sql} and _last_dlt_load_id in ({loads}) order by 1")
        assert [hour for (hour,) in rebuilt] == mart_hours
    assert pending_load_ids(warehouse_copy) == []


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


@pytest.mark.parametrize(
    ("source_dataset", "source_code", "intervals"),
    [("FUELINST", "CCGT", 12), ("PVLIVE", "SOLAR", 2)],
)
def test_an_hour_is_the_mean_of_the_intervals_published_in_it(seeded_warehouse, source_dataset, source_code, intervals):
    # the entity keeps each source's published interval (5 minutes, half hours); the mart conforms both to hours
    [(expected, published)] = query(
        seeded_warehouse,
        "select round(avg(generation_mw), 3), count(*) from ods.ods_generation_actual "
        f"where source_dataset = '{source_dataset}' and source_code = '{source_code}' "
        "and timestamp_utc >= timestamp '2024-03-04 10:00' and timestamp_utc < timestamp '2024-03-04 11:00'",
    )
    assert published == intervals
    assert query(
        seeded_warehouse,
        "select generation_mw, coverage from marts.mart_generation_actual "
        f"where source_dataset = '{source_dataset}' and source_code = '{source_code}' "
        "and timestamp_utc = timestamp '2024-03-04 10:00'",
    ) == [(expected, 1.0)]


def test_a_month_long_period_holds_in_every_hour_of_its_month(seeded_warehouse):
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
    assert "mart_demand_actual" not in audited
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


def test_a_first_build_by_hand_processes_every_load(tmp_path, monkeypatch):
    monkeypatch.setenv("POWER_DESK_PIPELINES_DIR", str(tmp_path / "pipelines"))  # no state from other tests' loads
    db = tmp_path / "fresh.duckdb"
    load_seed(db)
    assert run_dbt(["build"], db, target_path=tmp_path / "target") == 0
    assert query(db, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]


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
