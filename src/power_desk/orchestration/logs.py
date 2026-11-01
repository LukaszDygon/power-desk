"""Run logs in the log standard (docs/logging.md): JSON lines in `data/logs/<env>/dagster-runs.jsonl`.

Dagster hands every record of a run (its own events, and the `power_desk` and `dlt` loggers it manages) to
the handlers of `python_logs.dagster_handler_config` in `.dagster/<env>/dagster.yaml`, stamped with the run
id. The console keeps Dagster's own format, so no line is printed twice. On the local cluster, Alloy ships
the file to Loki (platform/README.md).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import warnings

from power_desk.settings import DATA_DIR, environment
import power_desk_logging


def run_log_handler() -> logging.Handler:
    """The handler `dagster.yaml` names: the run log, rotated at 50 MB."""
    path = DATA_DIR / "logs" / environment() / "dagster-runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=50_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(power_desk_logging.Formatter("orchestrator", json_format=True))
    return handler


def configure_run_logs() -> None:
    """The standard without handlers of ours: Dagster attaches them, from `dagster.yaml`."""
    power_desk_logging.instrument()
    # Dagster marks handlers from dagster.yaml as beta, warning on every run
    warnings.filterwarnings("ignore", message="Handling yaml-defined logging configuration")
