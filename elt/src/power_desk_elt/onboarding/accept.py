"""Acceptance run of a source: real data through the whole ELT into a fresh warehouse, measured and profiled.

    uv run power-desk-accept <source> --start-date YYYY-MM-DD --end-date YYYY-MM-DD [--label baseline]

In `data/onboarding/<source>/acceptance/` (replaced on every run), a warehouse gets the reference data the
dimensions need (the EIC seed) and the source's data for the window, through its own pipeline. Then:
- the same window is ingested again: idempotent when no raw table changes (rows, current versions)
- dbt builds and tests everything over the whole warehouse (`run_results.json`)
- each ods and mart relation holding the source's rows is profiled, sampled to CSV and timed on a
  daily aggregate; raw tables are profiled and sampled too
- the scheduled run is projected from the timings and compared with the interval of the source's ingest job
- `dlt.load` events are counted from the run's log (`accept.log`, the log standard as JSON lines)

Writes `acceptance.md` (criteria, timings, profile) and `acceptance.json`, and appends the timings to
`data/onboarding/<source>/timings.jsonl` under `--label`, for stratified comparisons (benchmark-pipeline skill).
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
import json
import logging
from logging.handlers import BufferingHandler
import os
from pathlib import Path
import shutil
import statistics
import sys
import time
from typing import Any
from unittest.mock import patch

from dagster._utils.schedules import get_smallest_cron_interval
import duckdb

from power_desk_elt.ingest.pipeline import DATASET_NAME, make_pipeline, make_source, run
from power_desk_elt.ingest.registry import SOURCES
from power_desk_elt.ingest.seed.load import load_seed
from power_desk_elt.onboarding.profile import ONBOARDING_DIR, columns_table, first_row, quoted, summarize
from power_desk_elt.orchestration.jobs import INGEST_JOBS
from power_desk_elt.transform.dbt import DbtRun, run_dbt, tests_downstream_of, unloaded_raw_tables
from power_desk_elt.transform.loads import pending_load_ids
import power_desk_logging
from power_desk_logging import EVENT_NAME, Formatter
from power_desk_warehouse import table_names

REFERENCE_SOURCES = ("entsoe_eic",)  # the dimensions' publishers, loaded from the seed
SCHEDULE_SHARE = 0.25  # a scheduled run may take at most this share of its job's interval
QUERY_SECONDS = 1.0  # a daily aggregate over the window
SAMPLE_ROWS = 200


@contextmanager
def isolated(out: Path, start: date) -> Iterator[list[logging.LogRecord]]:
    """dlt state, start date and schema exports kept out of the repo; the run's log records collected."""
    collect, to_file = BufferingHandler(capacity=sys.maxsize), logging.FileHandler(out / "accept.log")
    to_file.setFormatter(Formatter("accept", json_format=True))
    env = {
        "POWER_DESK_PIPELINES_DIR": str(out / "pipelines"),
        "POWER_DESK_START_DATE": start.isoformat(),
        "POWER_DESK_EXPORT_SCHEMAS": "0",
    }
    power_desk_logging.instrument()  # dlt loads logged as `dlt.load` events, whoever configured the handlers
    root = logging.getLogger()
    root.addHandler(collect)
    root.addHandler(to_file)
    try:
        with patch.dict(os.environ, env):
            yield collect.buffer
    finally:
        root.removeHandler(collect)
        root.removeHandler(to_file)


def timed(action: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    result = action(*args, **kwargs)
    return result, round(time.perf_counter() - started, 3)


def columns(con: duckdb.DuckDBPyConnection, relation: str) -> set[str]:
    return {c for (c,) in con.execute(f"select column_name from (describe {relation})").fetchall()}


def raw_state(con: duckdb.DuckDBPyConnection, tables: list[str]) -> dict[str, dict[str, Any]]:
    """Rows and current versions per raw table: equal before and after a repeated load when it is idempotent."""
    state = {}
    for table in tables:
        ref = f"{DATASET_NAME}.{quoted(table)}"
        versioned = "_dlt_valid_to" in columns(con, ref)
        current = "count(*) filter (where _dlt_valid_to is null)" if versioned else "count(*)"
        rows, current_rows = first_row(con, f"select count(*), {current} from {ref}")
        state[table] = {"rows": rows, "current": current_rows}
    return state


def relations_with(con: duckdb.DuckDBPyConnection, column: str, schemas: tuple[str, ...]) -> list[tuple[str, str]]:
    return con.execute(
        "select table_schema, table_name from information_schema.columns where column_name = ? "
        f"and table_schema in ({', '.join('?' for _ in schemas)}) order by all",
        [column, *schemas],
    ).fetchall()


def profile_relation(con: duckdb.DuckDBPyConnection, relation: str, where: str, out: Path) -> dict[str, Any]:
    """Rows, time span, `SUMMARIZE`, a CSV sample and the time of a daily aggregate of the measures."""
    rows = f"(select * from {relation} where {where})"
    count, first, last = first_row(con, f"select count(*), min(timestamp_utc), max(timestamp_utc) from {rows}")
    info: dict[str, Any] = {"rows": count, "first": first, "last": last}
    if not count:
        return info
    info["columns"] = summarize(con, rows)
    con.execute(
        f"copy (select * from {rows} order by timestamp_utc desc limit {SAMPLE_ROWS}) to '{out / relation}.csv'"
    )
    numeric = [c["column_name"] for c in info["columns"] if c["column_type"] in ("DOUBLE", "BIGINT", "INTEGER")]
    if numeric:
        aggregate = ", ".join(f"avg({quoted(c)})" for c in numeric if not c.startswith("_"))
        query = f"select date_trunc('day', timestamp_utc), {aggregate} from {rows} group by 1"
        info["daily_aggregate_s"] = statistics.median(timed(lambda: con.execute(query).fetchall())[1] for _ in range(3))
    return info


def dbt_results(target: Path) -> dict[str, list[str]]:
    results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))["results"]
    return {
        status: sorted(r["unique_id"].split(".")[2] for r in results if r["status"] == status)
        for status in ("fail", "error", "warn")
    }


def accept(source: str, start: date, end: date, label: str = "") -> dict[str, Any]:
    out = ONBOARDING_DIR / source / "acceptance"
    shutil.rmtree(out, ignore_errors=True)
    (out / "sample").mkdir(parents=True)
    db, target = out / "warehouse.duckdb", out / "target"
    with isolated(out, start) as records:
        if reference := [s for s in REFERENCE_SOURCES if s != source]:
            load_seed(db, sources=reference)
        pipeline, window = make_pipeline(source, db, schemas_dir=None), SOURCES[source].window(start, end)
        _, ingest_s = timed(run, pipeline, make_source(source, window))
        tables = sorted(pipeline.default_schema.data_table_names())
        with duckdb.connect(str(db), read_only=True) as con:
            before = raw_state(con, tables)
        _, repeat_s = timed(run, pipeline, make_source(source, window))
        run_dbt(["parse"], db, target)
        args = DbtRun(scope="all").args(pending_load_ids(db))
        if unloaded := unloaded_raw_tables(target / "manifest.json", db):
            args += ["--exclude", tests_downstream_of(unloaded)]
        dbt_code, dbt_s = timed(run_dbt, args, db, target)
    loads = [
        r for r in records if getattr(r, EVENT_NAME, None) == "dlt.load" and getattr(r, "dlt.pipeline_name") == source
    ]
    with duckdb.connect(str(db), read_only=True) as con:
        after = raw_state(con, tables)
        raw = {
            t: {
                **after[t],
                "columns": summarize(con, f"{DATASET_NAME}.{quoted(t)}"),
                "child": "_dlt_parent_id" in (dlt_columns := columns(con, f"{DATASET_NAME}.{quoted(t)}")),
                "versioned": "_dlt_valid_from" in dlt_columns,
            }
            for t in tables
        }
        for table in tables:
            sample = f"select * from {DATASET_NAME}.{quoted(table)} limit {SAMPLE_ROWS}"
            con.execute(f"copy ({sample}) to '{out / 'sample' / table}.csv'")
        datasets = []
        if "dim_source_dataset" in table_names(con, "dims"):
            registered = con.execute("select source_dataset from dims.dim_source_dataset where source = ?", [source])
            datasets = [d for (d,) in registered.fetchall()]
        where = f"source_dataset in ({', '.join(repr(d) for d in datasets) or 'null'})"
        relations = {
            f"{schema}.{name}": profile_relation(con, f"{schema}.{name}", where, out / "sample")
            for schema, name in relations_with(con, "source_dataset", ("ods", "marts"))
        }
    relations = {name: info for name, info in relations.items() if info["rows"]}
    job = next((j for j in INGEST_JOBS if set(j.tables) & set(tables)), None)
    days = (end - start).days + 1
    interval_s = get_smallest_cron_interval(job.cron).total_seconds() if job else None
    projected_s = round(ingest_s / days * max(1.0, (interval_s or 0) / 86400) + dbt_s, 1)
    result = {
        "source": source,
        "label": label,
        "window": {"start": start, "end": end, "days": days},
        "timings": {
            "ingest_s": ingest_s,
            "repeat_ingest_s": repeat_s,
            "dbt_build_s": dbt_s,
            "projected_run_s": projected_s,
        },
        "schedule": {"job": job.name if job else None, "cron": job.cron if job else None, "interval_s": interval_s},
        "dbt": {"exit_code": dbt_code, **dbt_results(target)},
        "loads_logged": len(loads),
        "source_datasets": datasets,
        "idempotent": before == after,
        "raw": raw,
        "relations": relations,
    }
    result["criteria"] = criteria(result)
    (out / "acceptance.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out / "acceptance.md").write_text(markdown(result, out), encoding="utf-8")
    with (ONBOARDING_DIR / source / "timings.jsonl").open("a", encoding="utf-8") as f:
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        timings = {k: v.get("daily_aggregate_s") for k, v in relations.items()}
        f.write(
            json.dumps({"at": stamp, "label": label, "days": days, **result["timings"], "queries_s": timings}) + "\n"
        )
    return result


def criteria(r: dict[str, Any]) -> list[dict[str, Any]]:
    """The checks a run can decide; the onboard-dataset skill adds the ones it cannot (code, docs, contracts)."""
    raw, relations, schedule = r["raw"], r["relations"], r["schedule"]
    json_columns = [
        f"{t}.{c['column_name']}" for t, info in raw.items() for c in info["columns"] if c["column_type"] == "JSON"
    ]
    unversioned = [t for t, info in raw.items() if not (info["versioned"] or info["child"])]
    slow = {k: v["daily_aggregate_s"] for k, v in relations.items() if v.get("daily_aggregate_s", 0) > QUERY_SECONDS}
    hourly = [k for k in relations if k.startswith("marts.")]
    budget = SCHEDULE_SHARE * schedule["interval_s"] if schedule["interval_s"] else None
    checks = [
        ("Loads every raw table", all(info["rows"] for info in raw.values()), {t: i["rows"] for t, i in raw.items()}),
        ("Structured: no JSON columns (nested data in child tables)", not json_columns, json_columns),
        ("Idempotent: a repeated load changes no raw table", r["idempotent"], "rows and current versions per table"),
        ("Time travel: raw tables versioned (scd2)", not unversioned, unversioned or "all versioned"),
        ("Logged: a dlt.load event per load", r["loads_logged"] >= 2, f"{r['loads_logged']} events for 2 runs"),
        (
            "dbt build and tests pass",
            r["dbt"]["exit_code"] == 0 and not r["dbt"]["fail"] + r["dbt"]["error"],
            {k: r["dbt"][k] for k in ("fail", "error", "warn")},
        ),
        ("Registered in dim_source_dataset", bool(r["source_datasets"]), r["source_datasets"]),
        ("Time series: rows reach an hourly mart", bool(hourly), hourly),
        (
            "Scheduled within budget",
            bool(budget) and r["timings"]["projected_run_s"] <= budget,
            f"projected {r['timings']['projected_run_s']} s, budget {budget} s ({schedule['job']})",
        ),
        (f"Daily aggregate under {QUERY_SECONDS} s", not slow, slow or "all under"),
    ]
    return [{"criterion": c, "passed": bool(ok), "evidence": e} for c, ok, e in checks]


def markdown(r: dict[str, Any], out: Path) -> str:
    window = r["window"]
    lines = [
        f"# Acceptance run: {r['source']} {r['label']}".rstrip(),
        "",
        f"Window {window['start']} .. {window['end']} ({window['days']} days); warehouse `{out / 'warehouse.duckdb'}`",
        "",
    ]
    lines += ["| | Criterion | Evidence |", "|---|---|---|"]
    lines += [f"| {'pass' if c['passed'] else 'FAIL'} | {c['criterion']} | {c['evidence']} |" for c in r["criteria"]]
    lines += ["", "## Timings (s)", "", *(f"- {k}: {v}" for k, v in r["timings"].items()), ""]
    lines += ["## Relations with the source's rows", ""]
    for name, info in [*((f"raw.{t}", i) for t, i in r["raw"].items()), *r["relations"].items()]:
        span = f", {info['first']} .. {info['last']}" if info.get("first") else ""
        query = f", daily aggregate {info['daily_aggregate_s']} s" if "daily_aggregate_s" in info else ""
        lines += [f"### {name}: {info['rows']} rows{span}{query}", "", *columns_table(info.get("columns", [])), ""]
    lines += [f"Samples: `{out / 'sample'}/<relation>.csv`."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True, help="inclusive")
    parser.add_argument("--label", default="", help="names the run in timings.jsonl, e.g. a variant and stratum")
    args = parser.parse_args()
    power_desk_logging.configure("accept")
    result = accept(args.source, args.start_date, args.end_date, args.label)
    print(markdown(result, ONBOARDING_DIR / args.source / "acceptance"))
    return 0 if all(c["passed"] for c in result["criteria"]) else 1


if __name__ == "__main__":
    sys.exit(main())
