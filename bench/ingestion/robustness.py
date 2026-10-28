"""Re-ingestion and failure scenarios for a file source like ENTSO-E's, loaded by dlt into DuckDB.

    python robustness.py                 # every scenario; prints and writes robustness_results.json
    python robustness.py <scenario> ...  # some of them

The source mimics the File Library: a monthly export re-published as versions (v2 revises 1% of v1's rows
with a later `update_time_utc`; v3 revises another 1%), loaded as row dicts in batches, with the files
already loaded kept in resource state (`source_files`, as `entsoe.file_partitions` does).
"""

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import dlt
import duckdb

LAB = Path(__file__).resolve().parent
WORK = LAB / "runs" / "robustness"
KEYS = 2000
KEY = ["date_time_utc", "area_code", "production_type"]
START = datetime(2024, 3, 1, tzinfo=UTC)
DISPOSITIONS = {
    "append": ("append", {}),
    "upsert": ({"disposition": "merge", "strategy": "upsert"}, {"primary_key": KEY}),
    "scd2": ({"disposition": "merge", "strategy": "scd2"}, {"merge_key": KEY}),
    "insert_only": ({"disposition": "merge", "strategy": "insert-only"}, {"primary_key": [*KEY, "update_time_utc"]}),
    # insert-only semantics through delete-insert, which deduplicates the staged rows on the primary key
    "delete_insert_version": (
        {"disposition": "merge", "strategy": "delete-insert"},
        {"primary_key": [*KEY, "update_time_utc"]},
    ),
}


def export(version: int, keys: int = KEYS) -> list[dict]:
    """The month as published in `version`: each later version revises another 1% of the keys."""
    rows = []
    for k in range(keys):
        revised = max(
            (v for v in range(2, version + 1) if (v - 2) * keys // 100 <= k < (v - 1) * keys // 100), default=1
        )
        rows.append(
            {
                "date_time_utc": START + timedelta(minutes=15 * k),
                "area_code": "10YGB----------A",
                "production_type": "Solar",
                "value_mw": float(100_000 * revised + k),
                "update_time_utc": START + timedelta(days=40 + revised),
            }
        )
    return rows


def files_resource(
    files: list[tuple[str, str, list[dict]]], disposition: str, fail_after_batches: int | None = None, batch: int = 500
):
    """Files not yet loaded in their published version, as batches; the version recorded once a file is done."""
    write_disposition, keys = DISPOSITIONS[disposition]

    def gen():
        loaded = dlt.current.resource_state().setdefault("source_files", {})
        batches = 0
        for name, last_updated, rows in files:
            if loaded.get(name) == last_updated:
                continue
            for i in range(0, len(rows), batch):
                if fail_after_batches is not None and batches == fail_after_batches:
                    raise RuntimeError("source failed mid-file")
                yield rows[i : i + batch]
                batches += 1
            loaded[name] = last_updated

    return dlt.resource(gen(), name="gen", write_disposition=write_disposition, **keys, file_format="parquet")


def make_pipeline(name: str) -> dlt.Pipeline:
    return dlt.pipeline(
        name,
        destination=dlt.destinations.duckdb(str(WORK / f"{name}.duckdb")),
        dataset_name="raw",
        pipelines_dir=str(WORK / "pipelines"),
    )


def fresh(name: str) -> dlt.Pipeline:
    shutil.rmtree(WORK / "pipelines" / name, ignore_errors=True)
    (WORK / f"{name}.duckdb").unlink(missing_ok=True)
    return make_pipeline(name)


def table(name: str, disposition: str) -> dict:
    """Rows, current keys, and how many current values come from a revision (v2 or v3) rather than v1."""
    path = WORK / f"{name}.duckdb"
    if not path.exists():
        return {"exists": False}
    with duckdb.connect(str(path), read_only=True) as con:
        tables = {
            t
            for (t,) in con.execute(
                "select table_name from information_schema.tables where table_schema = 'raw'"
            ).fetchall()
        }
        if "gen" not in tables:
            return {"exists": False}
        [(rows,)] = con.execute("select count(*) from raw.gen").fetchall()
        current = {
            "scd2": "select * from raw.gen where _dlt_valid_to is null",
            "insert_only": f"select * from raw.gen qualify row_number() over (partition by {', '.join(KEY)} order by update_time_utc desc) = 1",
            "append": f"select * from raw.gen qualify row_number() over (partition by {', '.join(KEY)} order by _dlt_load_id desc) = 1",
            "upsert": "select * from raw.gen",
            "delete_insert_version": f"select * from raw.gen qualify row_number() over (partition by {', '.join(KEY)} order by update_time_utc desc) = 1",
        }[disposition]
        [(keys, newest_value_keys)] = con.execute(
            f"select count(*), count(*) filter (where value_mw >= 200000) from ({current})"
        ).fetchall()
        [(loads,)] = con.execute("select count(*) from raw._dlt_loads").fetchall()
    return {
        "exists": True,
        "rows": rows,
        "current_keys": keys,
        "keys_showing_a_revision": newest_value_keys,
        "loads": loads,
    }


def local_files_state(pipeline: dlt.Pipeline) -> dict:
    resources = pipeline.state.get("sources", {}).get(pipeline.default_schema_name or "", {}).get("resources", {})
    return resources.get("gen", {}).get("source_files", {})


def replay_order() -> dict:
    """The revised export (v2) loads, then data from an older export (v1) arrives again under another name."""
    out = {}
    for disposition in DISPOSITIONS:
        name = f"replay_{disposition}"
        p = fresh(name)
        p.run(files_resource([("2024_03_r2", "t2", export(2))], disposition))
        after_v2 = table(name, disposition)
        p.run(files_resource([("2024_03_r2_copy", "t2", export(2))], disposition))  # the same version again
        after_redelivery = table(name, disposition)
        p.run(files_resource([("2024_03_r1_late", "t1", export(1))], disposition))  # an older version, late
        out[disposition] = {
            "after_v2": after_v2,
            "after_identical_redelivery": after_redelivery,
            "after_older_version": table(name, disposition),
        }
    return out


def extract_failure() -> dict:
    """The source raises after 2 of 4 batches."""
    name = "extract_failure"
    p = fresh(name)
    observed = {}
    try:
        p.run(files_resource([("2024_03", "t1", export(1))], "scd2", fail_after_batches=2))
    except Exception as exc:
        observed["error"] = type(exc).__name__
    observed["after_failure"] = {
        "destination": table(name, "scd2"),
        "local_source_files": local_files_state(p),
        "pending_packages": p.has_pending_data,
        "extracted_packages": list(p.list_extracted_load_packages()),
    }
    p.run(files_resource([("2024_03", "t1", export(1))], "scd2"))
    observed["after_rerun"] = {"destination": table(name, "scd2"), "local_source_files": local_files_state(p)}
    return observed


def child(script: str) -> subprocess.CompletedProcess:
    """Runs `script` in a new Python process with this module importable (a process that dies or exits)."""
    return subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(LAB)!r}); from robustness import *\n{script}"],
        capture_output=True,
        text=True,
        timeout=300,
    )


def crash_before_load() -> dict:
    """The process dies after normalize, before load; the next run brings a new export version (v2).
    An earlier month loaded first, so the dataset exists (a first-ever load is wiped instead: see destination_lost)."""
    name = "crash_before_load"
    fresh(name).run(files_resource([("2024_02", "t1", export(1))], "scd2"))
    died = child(
        f"p = make_pipeline({name!r}); p.extract(files_resource([('2024_03', 't1', export(1))], 'scd2')); p.normalize(); os._exit(1)"
    )
    p = make_pipeline(name)
    observed = {
        "child_exit": died.returncode,
        "pending_after_crash": p.has_pending_data,
        "destination_after_crash": table(name, "scd2"),
    }
    p.run(files_resource([("2024_03", "t2", export(2))], "scd2"))
    observed["after_next_run"] = table(name, "scd2")
    observed["local_source_files_after_next_run"] = local_files_state(p)
    p.run(files_resource([("2024_03", "t2", export(2))], "scd2"))
    observed["after_run_after_that"] = table(name, "scd2")
    return observed


def load_failure_lock() -> dict:
    """Another process holds the warehouse's write lock while the load runs; then it lets go."""
    name = "load_failure_lock"
    p = fresh(name)
    p.run(files_resource([("2024_02", "t1", export(1))], "scd2"))  # the database exists
    p.extract(files_resource([("2024_03", "t1", export(1, keys=KEYS))], "scd2"))
    p.normalize()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import duckdb, time; c = duckdb.connect({str(WORK / f'{name}.duckdb')!r}); print('held', flush=True); time.sleep(8)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    holder.stdout.readline()
    observed = {}
    try:
        p.load()
    except Exception as exc:
        root = exc
        while root.__cause__ or root.__context__:
            root = root.__cause__ or root.__context__
        observed["error"] = f"{type(exc).__name__} <- {type(root).__name__}"
    observed["pending_after_failure"] = p.has_pending_data
    holder.wait()
    observed["destination_while_pending"] = table(name, "scd2")
    p.load()
    observed["after_retry"] = table(name, "scd2")
    observed["pending_after_retry"] = p.has_pending_data
    return observed


def kill_during_load() -> dict:
    """The process is killed (SIGKILL) part way through a load of 100 files; the next run resumes it."""
    out = {}
    for delay in (0.3, 0.8, 1.5):
        for disposition in ("append", "scd2"):
            name = f"kill_{disposition}_{str(delay).replace('.', '_')}"
            fresh(name)
            script = (
                f"os.environ['DATA_WRITER__FILE_MAX_ITEMS'] = '2000'\n"
                f"p = make_pipeline({name!r}); rows = [r for v in range(1, 2) for r in export(v, keys=200000)]\n"
                f"p.extract(files_resource([('2024_03', 't1', rows)], {disposition!r}, batch=5000)); p.normalize()\n"
                f"print('loading', flush=True); p.load(); print('loaded', flush=True)"
            )
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    f"import sys, os; sys.path.insert(0, {str(LAB)!r}); from robustness import *\n{script}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            proc.stdout.readline()
            time.sleep(delay)
            proc.kill()
            proc.wait()
            p = make_pipeline(name)
            seen = {"pending_after_kill": p.has_pending_data, "destination_after_kill": table(name, disposition)}
            p.run(files_resource([("2024_03", "t1", export(1, keys=200000))], disposition, batch=5000))
            seen["after_rerun"] = table(name, disposition)
            out[name] = seen
    return out


def local_state_lost() -> dict:
    """The pipeline's working folder is deleted (a fresh container); the next run offers v1 and v2."""
    name = "local_state_lost"
    p = fresh(name)
    p.run(files_resource([("2024_03", "t1", export(1))], "append"))
    shutil.rmtree(WORK / "pipelines" / name)
    p = make_pipeline(name)
    p.run(files_resource([("2024_03", "t1", export(1))], "append"))  # the same export: a reload would duplicate it
    return {"after_rerun_same_export": table(name, "append"), "local_source_files": local_files_state(p)}


def destination_lost() -> dict:
    """The warehouse file is lost after v1 and v2 loaded; the publisher now offers only v3."""
    out = {}
    for disposition in ("scd2", "insert_only"):
        name = f"lost_{disposition}"
        p = fresh(name)
        p.run(files_resource([("2024_03", "t1", export(1))], disposition))
        p.run(files_resource([("2024_03", "t2", export(2))], disposition))
        before = table(name, disposition)
        # a copy of the Parquet files dlt kept for each completed package, outside the working folder
        backup = WORK / f"{name}_backup"
        shutil.rmtree(backup, ignore_errors=True)
        backup.mkdir()
        packages = sorted(p.list_completed_load_packages())
        for lid in packages:
            for job in p.get_load_package_info(lid).jobs["completed_jobs"]:
                if job.job_file_info.table_name == "gen" and job.file_path.endswith(".parquet"):  # not the merge SQL
                    shutil.copy(job.file_path, backup / f"{lid}__{Path(job.file_path).name}")
        (WORK / f"{name}.duckdb").unlink()
        p = make_pipeline(name)
        p.run(files_resource([("2024_03", "t2", export(2))], disposition))  # the publisher's current export, again
        naive = table(name, disposition)
        kept_after_naive_run = len(p.list_completed_load_packages())
        # recovery: replay the copied files, oldest package first, into a new warehouse
        import pyarrow.parquet as pq

        replay = [pq.read_table(f) for f in sorted(backup.iterdir())]
        (WORK / f"{name}.duckdb").unlink(missing_ok=True)
        shutil.rmtree(WORK / "pipelines" / name)
        p = make_pipeline(name)
        write_disposition, keys = DISPOSITIONS[disposition]
        for t in replay:
            p.run(dlt.resource([t], name="gen", write_disposition=write_disposition, **keys, file_format="parquet"))
        replayed = table(name, disposition)
        with duckdb.connect(str(WORK / f"{name}.duckdb"), read_only=True) as con:
            original_load_ids = con.execute("select count(distinct _dlt_load_id) from raw.gen").fetchall()[0][0]
        p.run(files_resource([("2024_03", "t3", export(3))], disposition))
        out[disposition] = {
            "before_loss": before,
            "rerun_after_loss": naive,
            "packages_before_loss": len(packages),
            "packages_left_after_rerun": kept_after_naive_run,
            "replayed_files": len(replay),
            "after_replay": replayed,
            "load_ids_in_table_after_replay": original_load_ids,
            "after_replay_and_v3": table(name, disposition),
        }
    return out


SCENARIOS = {
    f.__name__: f
    for f in (
        replay_order,
        extract_failure,
        crash_before_load,
        load_failure_lock,
        kill_during_load,
        local_state_lost,
        destination_lost,
    )
}


def duplicates(name: str) -> dict:
    """Rows beyond one per key and version: a job loaded twice shows here."""
    with duckdb.connect(str(WORK / f"{name}.duckdb"), read_only=True) as con:
        [(rows, distinct)] = con.execute(
            f"select count(*), count(distinct ({', '.join(KEY)}, update_time_utc)) from raw.gen"
        ).fetchall()
        cols = {
            c
            for (c,) in con.execute(
                "select column_name from information_schema.columns where table_name = 'gen'"
            ).fetchall()
        }
        open_versions = (
            con.execute(
                f"select count(*) from (select 1 from raw.gen where _dlt_valid_to is null group by {', '.join(KEY)} having count(*) > 1)"
            ).fetchall()[0][0]
            if "_dlt_valid_to" in cols
            else None
        )
    return {"rows": rows, "duplicate_rows": rows - distinct, "keys_with_two_open_versions": open_versions}


def kill_repeat() -> dict:
    """kill_during_load at more delays, counting duplicated rows after the resumed load."""
    out = {}
    delays = [float(d) for d in os.environ.get("KILL_DELAYS", "0.1,0.2,0.3,0.4,0.5,0.6").split(",")]
    for delay in delays:
        for disposition in os.environ.get("KILL_DISPOSITIONS", "append,scd2").split(","):
            name = f"killr_{disposition}_{str(delay).replace('.', '_')}"
            if os.environ.get("KILL_PRELOAD"):  # the table exists, as in production: a first 1,000 rows load before
                fresh(name).run(files_resource([("2024_02", "t1", export(1, keys=1000))], disposition))
            else:
                fresh(name)
            script = (
                f"os.environ['DATA_WRITER__FILE_MAX_ITEMS'] = '2000'\n"
                f"p = make_pipeline({name!r})\n"
                f"p.extract(files_resource([('2024_03', 't1', export(1, keys=200000))], {disposition!r}, batch=5000)); p.normalize()\n"
                f"print('loading', flush=True); p.load()"
            )
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    f"import sys, os; sys.path.insert(0, {str(LAB)!r}); from robustness import *\n{script}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            proc.stdout.readline()
            time.sleep(delay)
            proc.kill()
            proc.wait()
            p = make_pipeline(name)
            pending = p.has_pending_data
            p.load()
            out[name] = {"pending_after_kill": pending, **duplicates(name)}
    return out


SCENARIOS["kill_repeat"] = kill_repeat


if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    results = {}
    for scenario in sys.argv[1:] or SCENARIOS:
        started = time.perf_counter()
        try:
            results[scenario] = SCENARIOS[scenario]()
        except Exception as exc:
            results[scenario] = {"crashed": f"{type(exc).__name__}: {exc}"[:500]}
        results[scenario]["seconds"] = round(time.perf_counter() - started, 1)
        print(scenario, json.dumps(results[scenario], default=str), flush=True)
    (LAB / "robustness_results.json").write_text(json.dumps(results, indent=1, default=str))
