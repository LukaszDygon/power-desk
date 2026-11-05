"""Profile a dataset's sample files for onboarding: dlt's default normalization into DuckDB, then statistics.

    uv run power-desk-profile <name> <file>... [--records data.items] [--key a,b]... [--time col]
        [--published col] [--available-from YYYY-MM-DD]

Loads the files (JSON, JSON lines, CSV, Parquet; gzipped too) as one dlt resource `<name>` into the `raw`
schema of `data/onboarding/<source>/profile/<name>/profile.duckdb`, so nested data becomes child tables
(`<name>__<field>`) as it would in the warehouse. Then writes `profile.md` and `profile.json` there: per
table, its rows and DuckDB `SUMMARIZE`; on the root table, each candidate `--key` (exact repeats, and keys
with several distinct rows: revisions), the steps of the `--time` column, the cadence of `--published` and
its lag to `--time`, and the volume from `--available-from` to today: rows and bytes per sampled day (the
distinct UTC dates of `--published`, else of `--time`; so sample whole days). Column names are dlt's
(snake_case), as `profile.md` lists them.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from datetime import UTC, date, datetime
import gzip
import json
from pathlib import Path
import sys
from typing import Any

import dlt
from dlt.common.typing import TDataItems
from dlt.sources.filesystem.helpers import fetch_json
import duckdb

from power_desk_elt.settings import DATA_DIR

ONBOARDING_DIR = DATA_DIR / "onboarding"
DATASET = "raw"
BATCH_ROWS = 50_000
HORIZONS = {"month": 30, "year": 365}


def quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def first_row(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[Any, ...]:
    row = con.sql(sql).fetchone()
    assert row is not None, sql
    return row


def read_records(path: Path, records: str | None) -> Iterator[TDataItems]:
    """Batches of rows: JSON through Python (as sources fetch it), tables through DuckDB."""
    kind = next((s for s in reversed(path.suffixes) if s != ".gz"), "")
    if kind not in (".json", ".jsonl", ".ndjson"):
        with duckdb.connect() as con:
            yield from fetch_json(con.sql(f"select * from '{path}'"), BATCH_ROWS)
        return
    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    text = raw.decode("utf-8-sig")
    if kind != ".json":
        yield [json.loads(line) for line in text.splitlines() if line.strip()]
        return
    data = json.loads(text)
    for part in records.split(".") if records else []:
        data = data[part]
    yield data if isinstance(data, list) else [data]


def load(name: str, files: list[Path], records: str | None, out: Path) -> Path:
    """The files as resource `name`, normalized by dlt into a fresh DuckDB file."""
    db = out / "profile.duckdb"
    db.unlink(missing_ok=True)
    pipeline = dlt.pipeline(
        pipeline_name=f"profile_{name}",
        destination=dlt.destinations.duckdb(str(db)),
        dataset_name=DATASET,
        pipelines_dir=str(out / "pipelines"),
    )
    rows = dlt.resource((batch for path in files for batch in read_records(path, records)), name=name)
    pipeline.run(rows, write_disposition="replace", loader_file_format="parquet", refresh="drop_sources")
    return db


def summarize(con: duckdb.DuckDBPyConnection, table: str) -> list[dict[str, Any]]:
    """DuckDB `SUMMARIZE` of a table, without dlt's columns."""
    relation = con.sql(f"summarize {table}")
    rows = [dict(zip(relation.columns, row, strict=True)) for row in relation.fetchall()]
    return [r for r in rows if not r["column_name"].startswith("_dlt")]


def key_profile(con: duckdb.DuckDBPyConnection, table: str, key: list[str]) -> dict[str, Any]:
    """Rows, distinct keys, exact repeats, and keys with several distinct rows (revisions)."""
    cols = ", ".join(map(quoted, key))
    distinct = f"(select distinct * exclude (_dlt_load_id, _dlt_id) from {table})"
    rows, keys = first_row(con, f"select count(*), count(distinct ({cols})) from {table}")
    (distinct_rows,) = first_row(con, f"select count(*) from {distinct}")
    (revised,) = first_row(
        con, f"select count(*) from (select {cols} from {distinct} group by all having count(*) > 1)"
    )
    return {"key": key, "rows": rows, "keys": keys, "exact_repeats": rows - distinct_rows, "revised_keys": revised}


def steps(con: duckdb.DuckDBPyConnection, table: str, column: str) -> dict[str, Any]:
    """Span of a time column, and the most common steps between its distinct values."""
    values = f"(select distinct try_cast({quoted(column)} as timestamptz) as ts from {table} where ts is not null)"
    first, last, count = first_row(con, f"select min(ts), max(ts), count(*) from {values}")
    common = con.sql(
        f"select step, count(*) as n from (select ts - lag(ts) over (order by ts) as step from {values}) "
        "where step is not null group by step order by n desc, step limit 3"
    ).fetchall()
    return {"first": first, "last": last, "distinct": count, "steps": [{"step": s, "count": n} for s, n in common]}


def lag_hours(con: duckdb.DuckDBPyConnection, table: str, time: str, published: str) -> dict[str, Any]:
    """Hours from publication to the value's time (negative: published after it), and publications per time."""
    ts, pub = (f"try_cast({quoted(c)} as timestamptz)" for c in (time, published))
    ((p5, p50, p95),) = first_row(
        con, f"select quantile_cont(epoch({ts} - {pub}) / 3600, [0.05, 0.5, 0.95]) from {table}"
    )
    (per_time,) = first_row(con, f"select avg(n) from (select count(distinct {pub}) as n from {table} group by {ts})")
    return {"p5": p5, "p50": p50, "p95": p95, "publications_per_time": per_time}


def sampled_days(con: duckdb.DuckDBPyConnection, table: str, column: str) -> int:
    """Distinct UTC dates of a time column: the days the samples cover."""
    return first_row(con, f"select count(distinct try_cast({quoted(column)} as timestamptz)::date) from {table}")[0]


def volume(rows: int, days: int, input_bytes: int, available_from: date | None) -> dict[str, Any]:
    """Rows and download size per sampled day, and for each backfill horizon."""
    if not rows or not days:
        return {}
    per_day = {"rows": rows / days, "input_bytes": input_bytes / days}
    horizons = dict(HORIZONS)
    if available_from:
        horizons["all history"] = (datetime.now(UTC).date() - available_from).days
    return {
        "per_day": per_day,
        "horizons": {h: {"days": d, **{k: v * d for k, v in per_day.items()}} for h, d in horizons.items()},
    }


def profile(args: argparse.Namespace) -> dict[str, Any]:
    out = ONBOARDING_DIR / args.name.partition("__")[0] / "profile" / args.name
    out.mkdir(parents=True, exist_ok=True)
    files = [Path(f) for f in args.files]
    root = f"{DATASET}.{quoted(args.name)}"
    with duckdb.connect(str(load(args.name, files, args.records, out)), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        tables = con.execute(
            "select table_name from information_schema.tables where table_schema = ? "
            "and not starts_with(table_name, '_dlt') order by table_name",
            [DATASET],
        ).fetchall()
        result: dict[str, Any] = {
            "name": args.name,
            "files": [str(f) for f in files],
            "tables": {
                t: {
                    "rows": first_row(con, f"select count(*) from {DATASET}.{quoted(t)}")[0],
                    "columns": summarize(con, f"{DATASET}.{quoted(t)}"),
                }
                for (t,) in tables
            },
            "keys": [key_profile(con, root, k.split(",")) for k in args.key],
        }
        if args.time:
            result["time"] = steps(con, root, args.time)
        if cadence := args.published or args.time:
            input_bytes = sum(f.stat().st_size for f in files)
            rows, days = result["tables"][args.name]["rows"], sampled_days(con, root, cadence)
            result["volume"] = {"sampled_days": days, **volume(rows, days, input_bytes, args.available_from)}
        if args.published:
            result["published"] = steps(con, root, args.published)
            if args.time:
                result["lag_hours"] = lag_hours(con, root, args.time, args.published)
    (out / "profile.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out / "profile.md").write_text(markdown(result), encoding="utf-8")
    return result


def columns_table(columns: list[dict[str, Any]]) -> list[str]:
    """`SUMMARIZE` rows as a markdown table."""
    lines = ["| column | type | nulls % | distinct ~ | min | max |", "|---|---|---|---|---|---|"]
    return lines + [
        f"| {c['column_name']} | {c['column_type']} | {c['null_percentage']} | {c['approx_unique']} "
        f"| {c['min']} | {c['max']} |"
        for c in columns
    ]


def markdown(result: dict[str, Any]) -> str:
    lines = [f"# Profile: {result['name']}", "", f"Files: {', '.join(result['files'])}", ""]
    for table, info in result["tables"].items():
        lines += [f"## {table} ({info['rows']} rows)", "", *columns_table(info["columns"]), ""]
    for key in result["keys"]:
        lines.append(
            f"- key ({', '.join(key['key'])}): {key['keys']} keys in {key['rows']} rows, "
            f"{key['exact_repeats']} exact repeats, {key['revised_keys']} keys with several distinct rows"
        )
    for name in ("time", "published"):
        if span := result.get(name):
            common = ", ".join(f"{s['step']} x{s['count']}" for s in span["steps"])
            lines.append(f"- {name}: {span['first']} .. {span['last']}, {span['distinct']} distinct; steps {common}")
    if lag := result.get("lag_hours"):
        lines.append(
            f"- time minus publication, hours: p5 {lag['p5']:.1f}, median {lag['p50']:.1f}, p95 {lag['p95']:.1f}; "
            f"{lag['publications_per_time']:.2f} publications per time value"
        )
    if days := result.get("volume", {}).get("sampled_days"):
        lines.append(f"- volume from {days} sampled days (extrapolated to each horizon):")
    for horizon, est in result.get("volume", {}).get("horizons", {}).items():
        lines.append(
            f"  - backfill {horizon} ({est['days']} days): ~{est['rows']:,.0f} rows, "
            f"~{est['input_bytes'] / 1e6:,.1f} MB to fetch"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    parser.add_argument("name", help="dataset name, as its raw table will be: <source>__<dataset>")
    parser.add_argument("files", nargs="+", help="sample files fetched from the publisher")
    parser.add_argument("--records", help="dotted path to the row list in a JSON document, e.g. data or result.records")
    parser.add_argument(
        "--key", action="append", default=[], help="candidate natural key, comma-separated (repeatable)"
    )
    parser.add_argument("--time", help="the column holding the value's time")
    parser.add_argument("--published", help="the column holding the publication time")
    parser.add_argument("--available-from", type=date.fromisoformat, help="first date the publisher offers")
    print(markdown(profile(parser.parse_args())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
