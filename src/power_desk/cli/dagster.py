"""Start Dagster (`dg dev`) for the active environment, with its own instance in `.dagster/<env>`.

power-desk-dagster                       # dev: schedules and sensors stopped
POWER_DESK_ENV=prod power-desk-dagster   # prod: schedules and sensors running
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from power_desk.settings import dagster_home, environment, warehouse_path


def main() -> None:
    os.environ["DAGSTER_HOME"] = str(dagster_home())
    print(f"POWER_DESK_ENV={environment()}  DAGSTER_HOME={os.environ['DAGSTER_HOME']}  warehouse={warehouse_path()}")
    dg = Path(sys.executable).with_name("dg")
    os.execv(str(dg), [str(dg), "dev", *sys.argv[1:]])


if __name__ == "__main__":
    main()
