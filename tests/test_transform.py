"""dbt layer: load-id scoped incremental marts, duplication guards and completeness tests."""

from __future__ import annotations

from pathlib import Path

import dlt
import duckdb

from power_desk.ingest.pipelines import make_pipeline
from power_desk.transform import dbt_build_args, pending_load_ids, run_dbt

MARTS = {"mart_generation_mix", "mart_demand_vs_forecast", "mart_hourly_summary"}


def query(db: Path, sql: str) -> list[tuple]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def build(db: Path, tmp_path: Path, *extra: str, scope: str = "recent") -> int:
    args = [*dbt_build_args(pending_load_ids(db), orchestrator_run_id="test-run", scope=scope), *extra]
    return run_dbt(args, db_path=db, target_path=tmp_path / "target")


def load_indo_revision(db: Path, rows: list[dict]) -> str:
    """Merge INDO rows through dlt (same natural key as the seed) and return the load id."""
    resource = dlt.resource(rows, name="raw_indo", write_disposition="merge",
                            primary_key=["settlementDate", "settlementPeriod"])
    return make_pipeline("revision", db_path=db, export_schema=False).run(resource).loads_ids[0]


def indo_row(period: int, demand: int) -> dict:
    return {"dataset": "INDO", "publishTime": "2024-03-03T12:00:00Z", "startTime": "2024-03-03T00:00:00Z",
            "settlementDate": "2024-03-03", "settlementPeriod": period, "demand": demand}


def test_seed_build_populates_marts_and_audits_loads(seeded_warehouse):
    [(seed_load,)] = query(seeded_warehouse, "select load_id from raw._dlt_loads")
    audited = query(seeded_warehouse, f"select model_name from dlt_meta.dlt_load_audit where load_id = '{seed_load}'")
    assert {r[0] for r in audited} == MARTS
    assert query(seeded_warehouse, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
    # 7 days x 288 five-minute intervals; 7 x 48 settlement periods; 7 x 24 hours
    assert query(seeded_warehouse, "select count(*) from marts.mart_generation_mix") == [(2016,)]
    assert query(seeded_warehouse, "select count(*) from marts.mart_demand_vs_forecast") == [(336,)]
    assert query(seeded_warehouse, "select count(*) from marts.mart_hourly_summary") == [(168,)]


def test_incremental_build_recomputes_only_grains_touched_by_pending_loads(warehouse_copy, tmp_path):
    before = dict(query(warehouse_copy, "select settlement_period, _dbt_invocation_id from marts.mart_demand_vs_forecast "
                                        "where settlement_date = '2024-03-03'"))
    gen_invocations = query(warehouse_copy, "select distinct _dbt_invocation_id from marts.mart_generation_mix")

    load_id = load_indo_revision(warehouse_copy, [indo_row(10, 99_999), indo_row(11, 88_888)])
    assert pending_load_ids(warehouse_copy) == [load_id]
    assert build(warehouse_copy, tmp_path) == 0

    after = dict(query(warehouse_copy, "select settlement_period, _dbt_invocation_id from marts.mart_demand_vs_forecast "
                                       "where settlement_date = '2024-03-03'"))
    changed = {p for p in after if after[p] != before[p]}
    assert changed == {10, 11}
    assert query(warehouse_copy, "select actual_demand_mw, _last_dlt_load_id from marts.mart_demand_vs_forecast "
                                 "where settlement_date = '2024-03-03' and settlement_period = 10") == [(99_999.0, load_id)]
    # untouched mart keeps its rows; the hourly rollup only rebuilds the affected hour(s)
    assert query(warehouse_copy, "select distinct _dbt_invocation_id from marts.mart_generation_mix") == gen_invocations
    rebuilt_hours = query(warehouse_copy, "select hour_utc::text from marts.mart_hourly_summary "
                                          f"where _dbt_invocation_id = '{after[10]}' order by 1")
    # periods 10 and 11 start at 04:30 and 05:00 UTC (GMT)
    assert rebuilt_hours == [("2024-03-03 04:00:00",), ("2024-03-03 05:00:00",)]
    audit = query(warehouse_copy, f"select model_name, orchestrator_run_id from dlt_meta.dlt_load_audit where load_id = '{load_id}'")
    assert {r[0] for r in audit} == MARTS and {r[1] for r in audit} == {"test-run"}
    assert pending_load_ids(warehouse_copy) == []


def test_duplicate_raw_row_fails_guard_and_keeps_load_pending(warehouse_copy, tmp_path):
    con = duckdb.connect(str(warehouse_copy))
    con.execute("insert into raw._dlt_loads (load_id, schema_name, status, inserted_at) values ('1999999999.1', 'manual', 0, now())")
    # simulate a merge that appended instead of upserting: same natural key, new load id
    con.execute("""
        insert into raw.raw_indo
        select * replace ('1999999999.1' as _dlt_load_id, 'dup' as _dlt_id, demand + 1 as demand)
        from raw.raw_indo where settlement_date = '2024-03-05' and settlement_period = 20
    """)
    con.close()

    assert build(warehouse_copy, tmp_path) != 0
    # key-scoped guard: the new row duplicates a row from an older load
    assert query(warehouse_copy, "select settlement_date, settlement_period, n_rows "
                                 "from test_failures.raw_indo_unique_natural_key") == [("2024-03-05", 20, 2)]
    # the mart fed by the duplicated period failed its guards -> load stays pending for it
    audited = {r[0] for r in query(warehouse_copy, "select model_name from dlt_meta.dlt_load_audit where load_id = '1999999999.1'")}
    assert "mart_demand_vs_forecast" not in audited
    assert "1999999999.1" in pending_load_ids(warehouse_copy)


def test_completeness_flags_missing_settlement_period(warehouse_copy, tmp_path):
    con = duckdb.connect(str(warehouse_copy))
    con.execute("delete from raw.raw_indo where settlement_date = '2024-03-04' and settlement_period = 17")
    con.close()

    code = run_dbt(["test", "--select", "stg_bmrs__indo", "--vars", '{"dlt_scope": "all"}'],
                   db_path=warehouse_copy, target_path=tmp_path / "target")
    assert code != 0
    missing = query(warehouse_copy, "select settlement_date::text, settlement_period "
                                    "from test_failures.stg_bmrs__indo_no_missing_periods")
    assert missing == [("2024-03-04", 17)]


def test_scoped_tests_only_read_pending_rows(seeded_warehouse, tmp_path):
    code = run_dbt(["compile", "--select", "ods_demand_actual", "--vars", '{"dlt_load_ids": ["L1"]}'],
                   db_path=seeded_warehouse, target_path=tmp_path / "target")
    assert code == 0
    compiled = next((tmp_path / "target" / "compiled").rglob("not_null_ods_demand_actual_national_demand_mw.sql")).read_text()
    assert "_dlt_load_id in (select unnest(cast(['L1'] as varchar[])) as load_id)" in compiled


def test_manual_first_build_without_vars(tmp_path):
    """`dbt build` by hand on a fresh warehouse: tests scope to all completed loads."""
    from power_desk.ingest.seed import load_seed

    db = tmp_path / "fresh.duckdb"
    load_seed(db)
    assert run_dbt(["build"], db_path=db, target_path=tmp_path / "target") == 0
    assert query(db, "select count(*) from dlt_meta.dlt_pending_loads") == [(0,)]
