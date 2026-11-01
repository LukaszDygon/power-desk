"""Environment shared by every service, read from environment variables (and `.env` in the working directory).

| Variable | Default | |
|---|---|---|
| `POWER_DESK_LANDING_URL` | `data/landing` | landing zone (dlt filesystem `bucket_url`): a path or `s3://` URL |
| `POWER_DESK_SERVICES_PIPELINES_DIR` | `.dlt/services` | dlt working directory (disposable) |
| `POWER_DESK_PORT` | `8080` | HTTP port: the service's endpoints and `/healthz` |

Logging follows the log standard (`power_desk_logging`, docs/logging.md). Publisher and object-storage
credentials are dlt secrets (`SOURCES__<SOURCE>__...`, `DESTINATION__FILESYSTEM__CREDENTIALS__...`), resolved
from the environment, `.env` or `.dlt/secrets.toml`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)


def landing_url() -> str:
    url = os.environ.get("POWER_DESK_LANDING_URL") or "data/landing"
    return url if "://" in url else Path(url).resolve().as_posix()


def pipelines_dir() -> Path:
    return Path(os.environ.get("POWER_DESK_SERVICES_PIPELINES_DIR") or Path(".dlt") / "services")


def port() -> int:
    return int(os.environ.get("POWER_DESK_PORT") or 8080)
