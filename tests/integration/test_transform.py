"""dbt over the seed week: marts populated across sources, load-id scoped rebuilds, guards and completeness."""

from __future__ import annotations

from power_desk import warehouse
from power_desk.ingest.pipeline import make_pipeline, make_source, run
from power_desk.ingest.seed.load import load_seed
from power_desk.ingest.seed.replay import SeedPublishers, replay
from power_desk.transform.dbt import run_dbt
from power_desk.transform.loads import pending_load_ids, tracked_models
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
            make_source("bmrs", "2024-03-08", "2024-03-08", resources=["bmrs__indo"]),
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
        "select settlement_date, settlement_period, n_rows " "from test_failures.bmrs__indo_unique_natural_key",
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
        "select settlement_date::text, settlement_period " "from test_failures.stg_bmrs__indo_no_missing_periods",
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


def test_a_first_build_by_hand_processes_every_load(tmp_path):
    db = tmp_path / "fresh.duckdb"
    load_seed(db)
    assert run_dbt(["build"], db, target_path=tmp_path / "target") == 0
    assert query(db, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
