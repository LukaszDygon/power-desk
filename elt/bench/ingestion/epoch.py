"""Run an epoch of cases (case.py, or the case's `script`) one at a time (no contention), appending each result to results.jsonl.

python3 epoch.py <epoch name> cases/<cases.json>      # run (data: python prepare.py)
python3 epoch.py --table [<epoch name>]          # summarise results
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

LAB = Path(__file__).resolve().parent
RESULTS = LAB / "results.jsonl"
DEPS = [
    "dlt[pyiceberg,deltalake,duckdb,ducklake,sqlalchemy,filesystem]==1.30.0",
    "duckdb==1.5.5",
    "sqlglot==30.19.0",
    "psutil",
    "orjson",
]
TIMEOUT = 1200


def run(epoch: str, cases: list[dict]) -> None:
    for i, case in enumerate(cases, 1):
        deps = DEPS + case.get("extra_deps", [])
        cmd = [
            "uv",
            "run",
            "--no-project",
            "--quiet",
            *(a for d in deps for a in ("--with", d)),
            "python",
            case.get("script", "case.py"),
            json.dumps({k: v for k, v in case.items() if k not in ("extra_deps", "script")}),
        ]
        started = time.time()
        # its own process group, so a timeout stops the case itself and not only `uv`
        proc = subprocess.Popen(
            cmd, cwd=LAB, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
        )
        try:
            stdout, _ = proc.communicate(timeout=TIMEOUT)
            line = next((l for l in stdout.splitlines() if l.startswith("RESULT ")), None)
            result = (
                json.loads(line[7:])
                if line
                else {"config": case, "status": f"crashed: exit {proc.returncode}", "loads": []}
            )
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            result = {"config": case, "status": f"timeout after {TIMEOUT}s", "loads": []}
        result["epoch"], result["elapsed"] = epoch, round(time.time() - started, 1)
        with RESULTS.open("a") as f:
            f.write(json.dumps(result) + "\n")
        print(f"[{i}/{len(cases)}] {summary(result)}", flush=True)


def summary(r: dict) -> str:
    c = r["config"]
    label = f"{c.get('reader', 'json'):5} {c.get('transform', 'none'):4} {c.get('destination', 'duckdb'):8} {c.get('disposition', 'scd2'):19}"
    extras = ",".join(
        f"{k}={v}"
        for k, v in c.items()
        if k
        in (
            "fraction",
            "batch_rows",
            "buffer_max_items",
            "file_max_items",
            "normalize_workers",
            "load_workers",
            "naming",
            "file_format",
            "repeat",
            "duckdb_memory_limit",
        )
        and v not in (None, 1, 1.0, 50000, "parquet")
    )
    if "name" in c:
        extras = (c["name"] + " " + extras)[:40]
    loads = r.get("loads", [])
    if not loads:
        return f"{label} {extras:28} {r['status'][:110]}"
    first = loads[0]
    stages = " ".join(
        f"{s[0].upper()}{first[s]['wall']:>5}/{first[s]['cpu']:>5}" for s in ("extract", "normalize", "load")
    )
    walls = "/".join(f"{l['total_wall']:.1f}" for l in loads)
    ok = "ok " if r.get("correct") else ("BAD" if r.get("status") == "ok" else "ERR")
    rises = "/".join(str(max(l[s].get("rise_mb", 0) for l in loads)) for s in ("extract", "normalize", "load"))
    return (
        f"{label} {extras:40} {ok} loads {walls:>16}s | 1st wall/cpu {stages} | base {r.get('baseline_mb', '-')} "
        f"peak {r.get('peak_mb', 0):>5}MB rise E/N/L {rises} | rows {r.get('rows_total')}/{r.get('rows_current')}"
    )


def table(epoch: str | None) -> None:
    for line in RESULTS.read_text().splitlines():
        r = json.loads(line)
        if epoch in (None, r.get("epoch")):
            print(f"{r.get('epoch', ''):8} {summary(r)}")


if __name__ == "__main__":
    if sys.argv[1] == "--table":
        table(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        run(sys.argv[1], json.loads(Path(sys.argv[2]).read_text()))
