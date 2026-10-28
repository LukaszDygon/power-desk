"""One small-file case: `runs` pipeline runs of `rows` rows each, as near-real-time events would arrive.

    python micro.py '<json config>'

Config keys: destination (duckdb | ducklake | delta | sqlite | postgres), reader (json | arrow), disposition
(append | upsert), rows (per run), runs, batched (true: the same rows in one run), env (dlt settings as
environment variables), compact (true: compact the table files after the runs, where dlt offers it),
file_format (default: Parquet on DuckDB / DuckLake, CSV for Arrow on Postgres, else the destination's).

Prints one JSON line: per-run wall time (median, p95, by stage), the table's rows, the files behind the table
(column stores), the pipeline's local working folder, and the cost of reading the table back.
"""

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time

LAB = Path(__file__).resolve().parent
DEFAULTS = {
    "destination": "duckdb",
    "reader": "json",
    "disposition": "append",
    "rows": 1,
    "runs": 50,
    "batched": False,
    "env": {},
    "compact": False,
    "file_format": None,
}
config = {**DEFAULTS, **json.loads(sys.argv[1])}
name = config.get("name") or "micro_{destination}_{reader}_{disposition}_{rows}".format(**config)
work = LAB / "runs" / name
shutil.rmtree(work, ignore_errors=True)
work.mkdir(parents=True)
os.environ["DLT_DATA_DIR"] = str(work / "dlt_data")
os.environ["NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_LOAD_ID"] = "true"
os.environ.update({key: str(value) for key, value in config["env"].items()})

started_import = time.perf_counter()
import dlt  # noqa: E402
import pyarrow as pa  # noqa: E402

IMPORT_SECONDS = round(time.perf_counter() - started_import, 2)
POSTGRES = os.environ.get("LAB_POSTGRES_URL", "postgresql://lab@localhost:54329/lab")
START = datetime(2024, 3, 1, tzinfo=UTC)


def events(run: int, rows: int) -> list[dict]:
    """`rows` readings, as an ENTSO-E-like generation row each: one new quarter-hour per run and area."""
    at = START + timedelta(minutes=15 * run)
    return [
        {
            "date_time_utc": at,
            "area_code": f"10Y{i:013d}",
            "production_type": "Solar",
            "actual_generation_output_mw": float(run * 10 + i),
            "update_time_utc": at + timedelta(minutes=5),
        }
        for i in range(rows)
    ]


def item(rows: list[dict]):
    return pa.Table.from_pylist(rows) if config["reader"] == "arrow" else rows


def destination():
    d = config["destination"]
    if d == "duckdb":
        return dlt.destinations.duckdb(str(work / "db.duckdb")), {}
    if d == "ducklake":
        from dlt.destinations.impl.ducklake.configuration import DuckLakeCredentials

        creds = DuckLakeCredentials(
            "lab", catalog=f"sqlite:///{work / 'catalog.sqlite'}", storage=(work / "lake").as_uri()
        )
        return dlt.destinations.ducklake(credentials=creds), {}
    if d == "delta":
        return dlt.destinations.filesystem((work / "lake").as_uri()), {"table_format": "delta"}
    if d == "sqlite":
        return dlt.destinations.sqlalchemy(f"sqlite:///{work / 'db.sqlite'}"), {}
    if d == "postgres":
        return dlt.destinations.postgres(POSTGRES), {}
    raise ValueError(d)


KEY = ["date_time_utc", "area_code", "production_type"]
disposition, keys = {
    "append": ("append", {}),
    "upsert": ({"disposition": "merge", "strategy": "upsert"}, {"primary_key": KEY}),
}[config["disposition"]]
dest, hints = destination()
dataset_name = f"micro_{abs(hash(name)) % 10**8}" if config["destination"] == "postgres" else "raw"
pipeline = dlt.pipeline(
    f"lab_{name}"[:60], destination=dest, dataset_name=dataset_name, pipelines_dir=str(work / "pipelines")
)
file_format = (
    {"file_format": config["file_format"]}
    if config["file_format"]
    else {"file_format": "csv"}
    if config["destination"] == "postgres" and config["reader"] == "arrow"
    else ({"file_format": "parquet"} if config["destination"] in ("duckdb", "ducklake") else {})
)


def one_run(rows: list[dict]) -> dict:
    resource = dlt.resource(item(rows), name="gen", write_disposition=disposition, **keys, **hints, **file_format)
    timings = {}
    for stage, fn in (
        ("extract", lambda: pipeline.extract(resource)),
        ("normalize", pipeline.normalize),
        ("load", pipeline.load),
    ):
        started = time.perf_counter()
        fn()
        timings[stage] = time.perf_counter() - started
    timings["total"] = sum(timings.values())
    return timings


def folder_mb(path: Path, suffix: str = "") -> tuple[float, int]:
    files = [f for f in path.rglob(f"*{suffix}") if f.is_file()] if path.exists() else []
    return round(sum(f.stat().st_size for f in files) / 1e6, 2), len(files)


def summary(values: list[float]) -> dict:
    ordered = sorted(values)
    return {
        "median": round(statistics.median(ordered), 3),
        "p95": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
        "max": round(ordered[-1], 3),
    }


result = {"config": config, "import_seconds": IMPORT_SECONDS}
try:
    batches = [events(run, config["rows"]) for run in range(config["runs"])]
    if config["batched"]:
        batches = [[row for batch in batches for row in batch]]
    runs = [one_run(batch) for batch in batches]
    result["runs_made"] = len(runs)
    result["per_run"] = {
        stage: summary([r[stage] for r in runs]) for stage in ("extract", "normalize", "load", "total")
    }
    result["first_run"] = round(runs[0]["total"], 3)
    result["all_runs_seconds"] = round(sum(r["total"] for r in runs), 2)
    if config["compact"]:
        started = time.perf_counter()
        if config["destination"] == "delta":
            from dlt.common.libs.deltalake import get_delta_tables

            get_delta_tables(pipeline, "gen")["gen"].optimize.compact()
            get_delta_tables(pipeline, "gen")["gen"].vacuum(
                retention_hours=0, enforce_retention_duration=False, dry_run=False
            )
        elif config["destination"] == "ducklake":
            with pipeline.sql_client() as client:
                client.execute_sql("CALL ducklake_flush_inlined_data('lab')")
                client.execute_sql("CALL lab.merge_adjacent_files()")
                client.execute_sql("CALL ducklake_cleanup_old_files('lab', cleanup_all => true)")
        result["compact_seconds"] = round(time.perf_counter() - started, 2)
    dataset = pipeline.dataset()
    started = time.perf_counter()
    [(rows_total,)] = dataset("select count(*) from gen").fetchall()
    result["read_back_seconds"] = round(time.perf_counter() - started, 3)
    result["rows_total"] = rows_total
    result["rows_expected"] = config["rows"] * config["runs"]
    result["table_files"] = dict(zip(("mb", "count"), folder_mb(work / "lake", ".parquet"), strict=True))
    result["database_mb"] = round(sum(f.stat().st_size for f in work.glob("db.*")) / 1e6, 2)
    if config["destination"] == "postgres":
        with pipeline.sql_client() as client:
            [(size,)] = client.execute_sql(f"select pg_total_relation_size('{dataset_name}.gen')")
        result["database_mb"] = round(size / 1e6, 2)
    result["working_folder"] = dict(zip(("mb", "count"), folder_mb(work / "pipelines"), strict=True))
    result["status"] = "ok"
except Exception as exc:
    root = exc
    while root.__cause__ is not None:
        root = root.__cause__
    result["status"] = f"failed: {type(root).__name__}: {' '.join(str(root).split())[:300]}"
print("RESULT " + json.dumps(result, default=str))
