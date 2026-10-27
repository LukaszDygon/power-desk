#!/usr/bin/env python3
"""Start Dagster for the active environment.

    uv run python scripts/dagster.py                         # dev: schedules/sensors stopped
    POWER_DESK_ENV=prod uv run python scripts/dagster.py     # prod: schedules/sensors running

Sets DAGSTER_HOME to `.dagster/<env>` (unless already set) so run history, schedule state and
the warehouse file stay separate per environment, then runs `dg dev` with any extra arguments.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from power_desk.ingest.pipelines import REPO_ROOT, environment, warehouse_path


def main() -> None:
    env = environment()
    os.environ.setdefault("DAGSTER_HOME", str(REPO_ROOT / ".dagster" / env))
    print(f"POWER_DESK_ENV={env}  DAGSTER_HOME={os.environ['DAGSTER_HOME']}  warehouse={warehouse_path()}")
    dg = Path(sys.executable).with_name("dg")
    os.execv(str(dg), [str(dg), "dev", *sys.argv[1:]])


if __name__ == "__main__":
    main()
