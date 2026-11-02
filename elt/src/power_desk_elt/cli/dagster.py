"""Start Dagster (`dg dev`) for the active environment, with its own instance in `elt/.dagster/<env>`.

power-desk-dagster                       # dev: schedules and sensors stopped
POWER_DESK_ENV=prod power-desk-dagster   # prod: schedules and sensors running

Dagster and the dbt processes it starts inherit dbt's environment (target, absolute warehouse
path) and this virtualenv's executables on PATH.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from power_desk_elt.settings import ELT_ROOT, dagster_home, environment, warehouse_path
from power_desk_elt.transform.dbt import dbt_env


def main() -> None:
    dg = Path(sys.executable).with_name("dg")
    env = {
        **dbt_env(),
        "DAGSTER_HOME": str(dagster_home()),
        "PATH": os.pathsep.join([str(dg.parent), os.environ.get("PATH", "")]),
    }
    # dg reads the project (`[tool.dg]`) from the working directory's pyproject.toml
    os.chdir(ELT_ROOT)
    # flushed: execve replaces the process, dropping anything still buffered (output to a file or pipe)
    print(
        f"POWER_DESK_ENV={environment()}  DAGSTER_HOME={env['DAGSTER_HOME']}  warehouse={warehouse_path()}", flush=True
    )
    os.execve(dg, [str(dg), "dev", *sys.argv[1:]], env)


if __name__ == "__main__":
    main()
