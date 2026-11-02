"""One experiment case: an ENTSO-E month loaded by dlt three times (original, identical, 1% revised).

    python case.py '<json config>'

Config keys (defaults in DEFAULTS): reader (json: row dicts | arrow: Arrow batches | arrow_dlthash: Arrow
batches plus dlt's `add_row_hash_to_table`, needs pandas), transform (none | sql: rename in the reader
query), destination (duckdb | ducklake | iceberg | delta | sqlite | postgres), disposition (append | upsert | scd2 |
insert_only_version | delete_insert), fraction (of the month's rows), batch_rows, file_format,
buffer_max_items, file_max_items, normalize_workers, load_workers, naming, repeat (the export yielded n
times in one load), duckdb_memory_limit, loads (files to load in turn, default original, identical, revised),
env (further dlt settings as environment variables, e.g. `DATA_WRITER__DISABLE_COMPRESSION`), columns
(typed: every column's type declared up front), max_table_nesting, schema_contract, detections (none:
dlt's type detection off).

Prints one JSON line: per load and stage the wall time, CPU seconds (process + children) and peak RSS
(process + children, sampled every 50 ms), then the table's row counts and correctness checks.
"""

import json
import os
from pathlib import Path
import resource
import shutil
import sys
import threading
import time

import psutil

LAB = Path(__file__).resolve().parent
DEFAULTS = {
    "reader": "json",
    "transform": "none",
    "destination": "duckdb",
    "disposition": "scd2",
    "fraction": 1.0,
    "batch_rows": 50_000,
    "file_format": "parquet",
    "buffer_max_items": None,
    "file_max_items": None,
    "normalize_workers": None,
    "load_workers": None,
    "naming": None,
    "loads": ["month", "month", "month_revised"],
    "repeat": 1,
    "duckdb_memory_limit": None,
    "env": {},
    "columns": None,
    "max_table_nesting": None,
    "schema_contract": None,
    "detections": None,
}
config = {**DEFAULTS, **json.loads(sys.argv[1])}
name = config.get("name") or "_".join(str(config[k]) for k in ("reader", "transform", "destination", "disposition"))
work = LAB / "runs" / name
shutil.rmtree(work, ignore_errors=True)
work.mkdir(parents=True)

# dlt configuration through its environment variables, before dlt reads them
os.environ["DLT_DATA_DIR"] = str(work / "dlt_data")
for key, env in [
    ("buffer_max_items", "DATA_WRITER__BUFFER_MAX_ITEMS"),
    ("file_max_items", "DATA_WRITER__FILE_MAX_ITEMS"),
    ("normalize_workers", "NORMALIZE__WORKERS"),
    ("load_workers", "LOAD__WORKERS"),
    ("naming", "SCHEMA__NAMING"),
]:
    if config[key] is not None:
        os.environ[env] = str(config[key])
if config["normalize_workers"]:
    os.environ["NORMALIZE__START_METHOD"] = "spawn"
# Arrow tables get the dlt load id only when asked; the project's incremental models depend on it
os.environ["NORMALIZE__PARQUET_NORMALIZER__ADD_DLT_LOAD_ID"] = "true"
os.environ.update({key: str(value) for key, value in config["env"].items()})

import dlt  # noqa: E402
from dlt.sources.filesystem.helpers import fetch_json  # noqa: E402
import duckdb  # noqa: E402

PUBLISHED_KEY = ["DateTime(UTC)", "ResolutionCode", "AreaCode", "AreaTypeCode", "ProductionType"]
CLEAN = {
    "DateTime(UTC)": "date_time_utc",
    "ResolutionCode": "resolution_code",
    "AreaCode": "area_code",
    "AreaDisplayName": "area_display_name",
    "AreaTypeCode": "area_type_code",
    "AreaMapCode": "area_map_code",
    "ProductionType": "production_type",
    "ActualGenerationOutput[MW]": "actual_generation_output_mw",
    "ActualConsumption[MW]": "actual_consumption_mw",
    "UpdateTime(UTC)": "update_time_utc",
}


def column(published: str) -> str:
    return CLEAN[published] if config["transform"] == "sql" else published


def sizes() -> tuple[int, int]:
    """Rows per load, and how many of them the revised file re-publishes."""
    data = LAB / "data"
    with duckdb.connect() as con:
        [(n,)] = con.execute(f"select count(*) from read_csv('{data / 'month.csv'}', sep='\t')").fetchall()
        limit = int(n * config["fraction"])
        [(changed,)] = con.execute(f"""
            select count(*) from (select * from read_csv('{data / "month.csv"}', sep='\t') limit {limit}) a
            join (select * from read_csv('{data / "month_revised.csv"}', sep='\t') limit {limit}) b
              using ("DateTime(UTC)", ResolutionCode, AreaCode, AreaTypeCode, ProductionType)
            where a."UpdateTime(UTC)" <> b."UpdateTime(UTC)" """).fetchall()
    return limit, changed


LIMIT, CHANGED = sizes()


def export(file: str):
    """The export as published (`repeat` times), read by DuckDB; `transform=sql` renames columns in the query."""
    for _ in range(config["repeat"]):
        yield from export_once(file)


def export_once(file: str):
    con = duckdb.connect()
    path = LAB / "data" / f"{file}.csv"
    columns = "*" if config["transform"] == "none" else ", ".join(f'"{p}" as {c}' for p, c in CLEAN.items())
    relation = con.sql(f"select {columns} from read_csv('{path}', sep='\t') limit {LIMIT}")
    if config["reader"] in ("arrow", "arrow_dlthash"):
        yield from relation.to_arrow_reader(batch_size=config["batch_rows"])
    else:
        yield from fetch_json(relation, config["batch_rows"])
    con.close()


def destination():
    d = config["destination"]
    if d == "duckdb":
        if config["duckdb_memory_limit"]:
            con = duckdb.connect(str(work / "db.duckdb"), config={"memory_limit": config["duckdb_memory_limit"]})
            return dlt.destinations.duckdb(con), {}
        return dlt.destinations.duckdb(str(work / "db.duckdb")), {}
    if d == "ducklake":
        from dlt.destinations.impl.ducklake.configuration import DuckLakeCredentials

        creds = DuckLakeCredentials(
            "lab", catalog=f"sqlite:///{work / 'catalog.sqlite'}", storage=(work / "lake").as_uri()
        )
        return dlt.destinations.ducklake(credentials=creds), {}
    if d in ("iceberg", "delta"):
        return dlt.destinations.filesystem((work / "lake").as_uri()), {"table_format": d}
    if d == "sqlite":
        return dlt.destinations.sqlalchemy(f"sqlite:///{work / 'db.sqlite'}"), {}
    if d == "postgres":  # a local server; its URL in LAB_POSTGRES_URL
        return dlt.destinations.postgres(os.environ["LAB_POSTGRES_URL"]), {}
    raise ValueError(d)


natural_key = [column(c) for c in PUBLISHED_KEY]
disposition, keys = {
    "append": ("append", {}),
    "upsert": ({"disposition": "merge", "strategy": "upsert"}, {"primary_key": natural_key}),
    "delete_insert": ({"disposition": "merge", "strategy": "delete-insert"}, {"primary_key": natural_key}),
    "scd2": (
        {
            "disposition": "merge",
            "strategy": "scd2",
            **({"row_version_column_name": "row_hash"} if config["reader"] == "arrow_dlthash" else {}),
        },
        {"primary_key": natural_key, "merge_key": natural_key},
    ),
    "insert_only_version": (
        {"disposition": "merge", "strategy": "insert-only"},
        {"primary_key": [*natural_key, column("UpdateTime(UTC)")]},
    ),
    # the same rows as insert_only_version; delete-insert also deduplicates the staged rows
    "delete_insert_version": (
        {"disposition": "merge", "strategy": "delete-insert"},
        {"primary_key": [*natural_key, column("UpdateTime(UTC)")]},
    ),
}[config["disposition"]]


def typed_columns() -> dict[str, dict[str, str]]:
    """Every column's dlt type, from DuckDB's reading of the export."""
    dlt_types = {"TIMESTAMP": "timestamp", "VARCHAR": "text", "DOUBLE": "double", "BIGINT": "bigint"}
    with duckdb.connect() as con:
        relation = con.sql(f"select * from read_csv('{LAB / 'data' / 'month.csv'}', sep='\t') limit 1")
        hints = {
            column(c): {"data_type": dlt_types[str(t)]} for c, t in zip(relation.columns, relation.types, strict=True)
        }
    if config["reader"] == "arrow_dlthash":
        hints["row_hash"] = {"data_type": "text"}
    return hints


resource_hints = {
    key: value
    for key, value in {
        "columns": typed_columns() if config["columns"] == "typed" else None,
        "max_table_nesting": config["max_table_nesting"],
        "schema_contract": config["schema_contract"],
    }.items()
    if value is not None
}
dest, table_hints = destination()
# one dataset per case on a shared server
dataset_name = f"lab_{abs(hash(name)) % 10**8}" if config["destination"] == "postgres" else "raw"
pipeline = dlt.pipeline(
    f"lab_{name}"[:60], destination=dest, dataset_name=dataset_name, pipelines_dir=str(work / "pipelines")
)


class Sampler:
    """Peak RSS of this process and its children while a stage runs."""

    def __init__(self):
        self.peak, self._stop = 0, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        me = psutil.Process()
        while not self._stop.is_set():
            try:
                rss = me.memory_info().rss + sum(c.memory_info().rss for c in me.children(recursive=True))
            except psutil.Error:
                rss = 0
            self.peak = max(self.peak, rss)
            time.sleep(0.05)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def cpu() -> float:
    s, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime


def rss() -> int:
    me = psutil.Process()
    return me.memory_info().rss + sum(c.memory_info().rss for c in me.children(recursive=True))


def files_written(folder: str) -> dict:
    """The files a stage leaves for the next one: MB, count, extensions, Parquet compression and row groups."""
    files = [f for f in (Path(pipeline.working_dir) / folder).rglob("*") if f.is_file() and "new_jobs" in f.parts]
    written = {
        "mb": round(sum(f.stat().st_size for f in files) / 1e6, 1),
        "count": len(files),
        "formats": sorted({".".join(f.name.split(".")[-2:]) for f in files}),
    }
    if parquet := [f for f in files if ".parquet" in f.name]:
        import pyarrow.parquet as pq

        meta = pq.ParquetFile(parquet[0]).metadata
        written["parquet"] = {"compression": meta.row_group(0).column(0).compression, "row_groups": meta.num_row_groups}
    return written


def stage(fn, folder: str | None = None):
    started_wall, started_cpu, started_rss = time.perf_counter(), cpu(), rss()
    with Sampler() as sampler:
        fn()
    written = {"files": files_written(folder)} if folder else {}
    return {
        **written,
        "wall": round(time.perf_counter() - started_wall, 2),
        "cpu": round(cpu() - started_cpu, 2),
        "peak_mb": round(sampler.peak / 1e6),
        "start_mb": round(started_rss / 1e6),
        "rise_mb": round((sampler.peak - started_rss) / 1e6),
    }


result = {
    "config": {k: v for k, v in config.items() if k != "loads"},
    "rows_per_load": LIMIT * config["repeat"],
    "revised_rows": CHANGED,
    "baseline_mb": round(rss() / 1e6),
    "loads": [],
}
try:
    for file in config["loads"]:
        resource_ = dlt.resource(
            export(file),
            name="gen",
            write_disposition=disposition,
            **keys,
            **table_hints,
            **resource_hints,
            **({"file_format": config["file_format"]} if config["file_format"] != "default" else {}),
        )
        if config["reader"] == "arrow_dlthash":  # dlt's documented scd2 row hash for tabular data (pandas)
            from dlt.sources.helpers.transform import add_row_hash_to_table

            resource_.add_map(add_row_hash_to_table("row_hash"))
        load = {"file": file}
        schema = None
        if config["detections"] == "none" and not result["loads"]:
            schema = dlt.Schema(pipeline.pipeline_name)
            for detection in list(schema.settings.get("detections", [])):
                schema.remove_type_detection(detection)
        load["extract"] = stage(lambda: pipeline.extract(resource_, schema=schema), "normalize/extracted")
        load["normalize"] = stage(lambda: pipeline.normalize(), "load/normalized")
        load["load"] = stage(lambda: pipeline.load())
        load["total_wall"] = round(sum(load[s]["wall"] for s in ("extract", "normalize", "load")), 2)
        result["loads"].append(load)
    dataset = pipeline.dataset()
    table = dataset["gen"]
    columns = list(table.columns_schema.keys()) if hasattr(table, "columns_schema") else []
    current = " where _dlt_valid_to is null" if "_dlt_valid_to" in columns else ""
    [(total,)] = dataset("select count(*) from gen").fetchall()
    [(current_rows,)] = dataset(f"select count(*) from gen{current}").fetchall()
    result["rows_total"], result["rows_current"] = total, current_rows
    # the cost of reading the current version of every row, as a downstream model would
    key_sql = ", ".join(
        dlt.common.normalizers.naming.snake_case.NamingConvention().normalize_identifier(k)
        if config["naming"] in (None, "snake_case")
        else k
        for k in natural_key
    )
    update_col = [c for c in columns if c.startswith("update_time_utc")][0]
    current_sql = {
        "scd2": "select count(*) from gen where _dlt_valid_to is null",
        "upsert": "select count(*) from gen",
        "delete_insert": "select count(*) from gen",
    }.get(
        config["disposition"],
        f"select count(*) from (select 1 from gen qualify row_number() over "
        f"(partition by {key_sql} order by {update_col} desc) = 1)",
    )
    started = time.perf_counter()
    [(current_view_rows,)] = dataset(current_sql).fetchall()
    result["current_query"] = {"seconds": round(time.perf_counter() - started, 2), "rows": current_view_rows}
    expected = {
        "append": (3 * LIMIT, 3 * LIMIT),
        "upsert": (LIMIT, LIMIT),
        "delete_insert": (LIMIT, LIMIT),
        "scd2": (LIMIT + CHANGED, LIMIT),
        # every version is a row; the current one (latest UpdateTime per key) is chosen downstream
        "insert_only_version": (LIMIT + CHANGED, LIMIT + CHANGED),
        "delete_insert_version": (LIMIT + CHANGED, LIMIT + CHANGED),
    }[config["disposition"]]
    if config["repeat"] != 1 or config["loads"] != DEFAULTS["loads"]:
        expected = None
    result["expected"] = expected
    result["correct"] = expected is None or (total, current_rows) == tuple(expected)
    result["status"] = "ok"
except Exception as exc:
    root = exc
    while root.__cause__ is not None:
        root = root.__cause__
    result["status"] = f"failed: {type(root).__name__}: {' '.join(str(root).split())[:300]}"
result["peak_mb"] = round(
    max([l[s]["peak_mb"] for l in result["loads"] for s in ("extract", "normalize", "load")] or [0])
)
result["disk_mb"] = round(
    sum(
        f.stat().st_size
        for f in work.rglob("*")
        if f.is_file() and "dlt_data" not in f.parts and "pipelines" not in f.parts
    )
    / 1e6
)
if config["destination"] == "postgres" and result["status"] == "ok":  # the table and its indexes, on the server
    with pipeline.sql_client() as client:
        [(size,)] = client.execute_sql(f"select pg_total_relation_size('{dataset_name}.gen')")
    result["disk_mb"] = round(size / 1e6)
print("RESULT " + json.dumps(result))
