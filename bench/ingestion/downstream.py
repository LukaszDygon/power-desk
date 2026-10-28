"""Downstream cost of keeping versions: scd2 vs insert-only raw tables, at several duplication profiles.

    python downstream.py [profile ...]        # default: every profile; appends to downstream_results.jsonl

For each profile, a raw table holds ROWS versions spread over keys as the profile says (uniform 1, 2, 100,
1000 versions per key, or uneven), in both layouts dlt produces:
- scd2: every version with `_dlt_valid_from` / `_dlt_valid_to` (the current one open)
- insert-only: every version, primary key = natural key + `update_time_utc`
The history is written with SQL in load order (version j of every key in load j), into a table dlt created.
Then, timed: building the current-version mart in full; a dlt load of BATCH new versions on top of the
history (the merge cost against it); applying that load to the mart incrementally; an as-of query; deriving
validity windows from insert-only rows; and the database size.
"""

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import random
import shutil
import sys
import time

import dlt
import duckdb

LAB = Path(__file__).resolve().parent
RESULTS = LAB / os.environ.get("DOWNSTREAM_RESULTS", "downstream_results.jsonl")
ROWS = int(os.environ.get("DOWNSTREAM_ROWS", 5_000_000))  # smaller for a smoke test
BATCH = 5_000
KEY = ["date_time_utc", "area_code", "production_type"]
QUARTER_HOURS_PER_YEAR = 35_040

# profile -> SQL for its keys: k (key number), v (versions of the key)
PROFILES = {
    "uniform_1": f"select range as k, 1 as v from range({ROWS})",
    "uniform_2": f"select range as k, 2 as v from range({ROWS // 2})",
    "uniform_100": f"select range as k, 100 as v from range({ROWS // 100})",
    "uniform_1000": f"select range as k, 1000 as v from range({ROWS // 1000})",
    # mean 100: 90% of keys one version, 10% of keys about 991
    "skew_90_10": f"select range as k, case when range < 5000 then {(ROWS - 45_000) // 5000} else 1 end as v from range(50000)",
    # mean 100: 99% of keys one version, 1% of keys about 9,901
    "skew_99_1": f"select range as k, case when range < 500 then {(ROWS - 49_500) // 500} else 1 end as v from range(50000)",
    # mean about 100, Zipf (s = 1): the top key holds about 440,000 versions, the median key about 9
    "zipf": f"select range as k, greatest(1, round({ROWS / 11.4} / (range + 1)))::int as v from range(50000)",
}

KEY_COLUMNS = f"""
    timestamptz '2024-01-01 00:00:00+00' + to_minutes((15 * (k % {QUARTER_HOURS_PER_YEAR}))::bigint) as date_time_utc,
    '10Y' || lpad((k // {QUARTER_HOURS_PER_YEAR})::varchar, 13, '0') as area_code,
    'Solar' as production_type"""


def key_row(k: int) -> dict:
    return {
        "date_time_utc": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * (k % QUARTER_HOURS_PER_YEAR)),
        "area_code": f"10Y{k // QUARTER_HOURS_PER_YEAR:013d}",
        "production_type": "Solar",
    }


def history_sql(layout: str) -> str:
    """Every version of every key, in load order, as dlt's columns for `layout`."""
    validity = (
        """, to_timestamp(1700000000 + j) as _dlt_valid_from,
        case when j < v - 1 then to_timestamp(1700000000 + j + 1) end as _dlt_valid_to"""
        if layout == "scd2"
        else ""
    )
    return f"""
        select {KEY_COLUMNS},
            (hash(k, j) % 100000) / 10.0 as value_mw,
            timestamptz '2024-01-01 00:05:00+00' + to_minutes((15 * (k % {QUARTER_HOURS_PER_YEAR}) + 60 * j)::bigint) as update_time_utc,
            (1700000000 + j)::varchar as _dlt_load_id,
            md5(k::varchar || '-' || j::varchar) as _dlt_id{validity}
        from (select k, v, unnest(range(v)) as j from keys)
        order by j, k"""


def timed(con: duckdb.DuckDBPyConnection, sql: str, repeat: int = 2) -> float:
    """Best of `repeat` runs of `sql` (a statement that rebuilds its own output)."""
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        con.execute(sql)
        best = min(best, time.perf_counter() - started)
    return round(best, 3)


KEY_LIST = ", ".join(KEY)
KEY_JOIN = " and ".join(f"m.{c} = n.{c}" for c in KEY)
MARTS = {
    "scd2": {
        "current_filter": "create or replace table mart as select * exclude (_dlt_valid_from, _dlt_valid_to) from raw.gen where _dlt_valid_to is null",
    },
    "insert_only": {
        "current_row_number": f"create or replace table mart as select * from raw.gen qualify row_number() over (partition by {KEY_LIST} order by update_time_utc desc) = 1",
        "current_arg_max": f"create or replace table mart_argmax as select {KEY_LIST}, arg_max(value_mw, update_time_utc) as value_mw, max(update_time_utc) as update_time_utc from raw.gen group by all",
        "current_distinct_on": f"create or replace table mart_distinct as select distinct on ({KEY_LIST}) * from raw.gen order by {KEY_LIST}, update_time_utc desc",
    },
}


def incremental_sql(layout: str, last_load: str) -> list[str]:
    """Apply loads after `last_load` to the mart: replace the keys they touch with their newest version."""
    newest = (
        f"select * exclude (_dlt_valid_from, _dlt_valid_to) from raw.gen where _dlt_load_id > '{last_load}' and _dlt_valid_to is null"
        if layout == "scd2"
        else f"select * from raw.gen where _dlt_load_id > '{last_load}' qualify row_number() over (partition by {KEY_LIST} order by update_time_utc desc) = 1"
    )
    return [
        f"create or replace temp table new_rows as {newest}",
        f"delete from mart m using new_rows n where {KEY_JOIN}",
        "insert into mart select * from new_rows",
    ]


def as_of_sql(layout: str) -> str:
    """Every key's version as of the second load."""
    if layout == "scd2":
        return (
            "create or replace temp table as_of as select * from raw.gen where _dlt_valid_from <= to_timestamp(1700000001)"
            " and (_dlt_valid_to is null or _dlt_valid_to > to_timestamp(1700000001))"
        )
    return (
        f"create or replace temp table as_of as select * from raw.gen where _dlt_load_id <= '1700000001'"
        f" qualify row_number() over (partition by {KEY_LIST} order by update_time_utc desc) = 1"
    )


def run_profile(profile: str) -> list[dict]:
    work = LAB / "runs" / f"downstream_{profile}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    os.environ["DLT_DATA_DIR"] = str(work / "dlt_data")
    results = []
    for layout in ("scd2", "insert_only"):
        db = work / f"{layout}.duckdb"
        disposition, keys = (
            ({"disposition": "merge", "strategy": "scd2"}, {"merge_key": KEY})
            if layout == "scd2"
            else ({"disposition": "merge", "strategy": "insert-only"}, {"primary_key": [*KEY, "update_time_utc"]})
        )
        pipeline = dlt.pipeline(
            f"downstream_{profile}_{layout}",
            destination=dlt.destinations.duckdb(str(db)),
            dataset_name="raw",
            pipelines_dir=str(work / "pipelines"),
        )

        def load(rows: list[dict]):
            resource = dlt.resource(rows, name="gen", write_disposition=disposition, **keys, file_format="parquet")
            stages = {}
            for stage, fn in (
                ("extract", lambda: pipeline.extract(resource)),
                ("normalize", pipeline.normalize),
                ("load", pipeline.load),
            ):
                started = time.perf_counter()
                fn()
                stages[stage] = round(time.perf_counter() - started, 3)
            return stages

        # dlt creates the table and its columns; the history replaces its one row
        load([{**key_row(0), "value_mw": 0.0, "update_time_utc": key_row(0)["date_time_utc"]}])
        result = {"profile": profile, "layout": layout}
        with duckdb.connect(str(db)) as con:
            con.execute(f"create temp table keys as {PROFILES[profile]}")
            [(keys_n, rows_n, max_versions)] = con.execute("select count(*), sum(v), max(v) from keys").fetchall()
            result.update(keys=keys_n, rows=int(rows_n), max_versions=max_versions)
            con.execute("delete from raw.gen")
            started = time.perf_counter()
            con.execute(f"insert into raw.gen by name {history_sql(layout)}")
            result["write_history_s"] = round(time.perf_counter() - started, 2)
            con.execute("checkpoint")
            [(last_load,)] = con.execute("select max(_dlt_load_id) from raw.gen").fetchall()
            result["raw_mb"] = round(db.stat().st_size / 1e6, 1)
            result["marts_full_s"] = {name: timed(con, sql) for name, sql in MARTS[layout].items()}
            [(mart_rows,)] = con.execute("select count(*) from mart").fetchall()
            result["mart_rows"] = mart_rows
            con.execute("checkpoint")
            result["db_with_mart_mb"] = round(db.stat().st_size / 1e6, 1)
        # a new version for BATCH keys picked at random (uniform over keys), as one dlt load on top of the history
        picks = random.Random(7).sample(range(keys_n), min(BATCH, keys_n))
        batch = [
            {**key_row(k), "value_mw": -1.0, "update_time_utc": key_row(k)["date_time_utc"] + timedelta(days=400)}
            for k in picks
        ]
        result["batch_rows"] = len(batch)
        result["dlt_load_batch_s"] = load(batch)
        with duckdb.connect(str(db)) as con:
            started = time.perf_counter()
            for sql in incremental_sql(layout, last_load):
                con.execute(sql)
            result["mart_incremental_s"] = round(time.perf_counter() - started, 3)
            [(after,)] = con.execute("select count(*) from mart").fetchall()
            result["mart_rows_after"] = after
            [(current_raw,)] = con.execute(
                "select count(*) from raw.gen where _dlt_valid_to is null"
                if layout == "scd2"
                else f"select count(distinct ({KEY_LIST})) from raw.gen"
            ).fetchall()
            result["incremental_correct"] = after == current_raw
            result["as_of_s"] = timed(con, as_of_sql(layout))
            if layout == "insert_only":
                result["validity_windows_s"] = timed(
                    con,
                    f"create or replace temp table windows as select *, lead(update_time_utc) over (partition by {KEY_LIST} order by update_time_utc) as valid_to from raw.gen",
                )
            con.execute("checkpoint")
        results.append(result)
        print(json.dumps(result), flush=True)
    return results


if __name__ == "__main__":
    for profile in sys.argv[1:] or PROFILES:
        for result in run_profile(profile):
            with RESULTS.open("a") as f:
                f.write(json.dumps(result) + "\n")
