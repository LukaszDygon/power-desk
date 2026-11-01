"""The Power Desk log standard (docs/logging.md): one record format for every process, joinable to dlt and dbt.

A process calls `configure(service)` once (or `instrument()` where a framework owns the handlers, as Dagster
does); modules then log with `logging.getLogger(__name__)` and plain messages. Shared code adds context:
`log_context` binds attributes for a block, and dlt pipeline runs bind theirs and log their loads
(`dlt_tracking`).

| Variable | Default | |
|---|---|---|
| `POWER_DESK_ENV` | `dev` | `deployment.environment.name` of every record |
| `POWER_DESK_LOG_LEVEL` | `INFO` | our loggers and libraries; dlt's own level is `RUNTIME__LOG_LEVEL` (`WARNING`) |
| `POWER_DESK_LOG_FORMAT` | `text` | `text` (a line for people), or `json` (one object per line, for collectors) |
"""

from __future__ import annotations

import logging
import os
import sys
from types import TracebackType

from power_desk_logging.context import log_context
from power_desk_logging.formatter import EVENT_NAME, Formatter

__all__ = ["EVENT_NAME", "Formatter", "configure", "instrument", "log_context", "log_level"]


def log_level() -> str:
    return os.environ.get("POWER_DESK_LOG_LEVEL", "INFO").upper()


class ToRootHandlers(logging.Handler):
    """Hands records to the root logger's handlers: dlt logs to its own logger, which does not propagate."""

    def emit(self, record: logging.LogRecord) -> None:
        for handler in logging.getLogger().handlers:
            if record.levelno >= handler.level:
                handler.handle(record)


def instrument() -> None:
    """Our loggers at the standard level; dlt's records through our handlers (dlt keeps the first handler of
    its logger) and its pipeline runs enriched and logged."""
    from power_desk_logging import dlt_tracking

    logging.getLogger().setLevel(log_level())
    logging.getLogger("dlt").handlers = [ToRootHandlers()]
    dlt_tracking.register()


def log_uncaught(kind: type[BaseException], error: BaseException, traceback: TracebackType | None) -> None:
    """`sys.excepthook`: an exception that ends the process is a record too, not a bare traceback."""
    if issubclass(kind, KeyboardInterrupt):
        sys.__excepthook__(kind, error, traceback)
        return
    logging.getLogger(__name__).critical("stopped on %s: %s", kind.__name__, error, exc_info=(kind, error, traceback))


def configure(service: str) -> None:
    """Log every record of this process, dlt's and uncaught exceptions included, to stderr in the standard."""
    handler = logging.StreamHandler()
    handler.setFormatter(Formatter(service))
    logging.basicConfig(handlers=[handler], force=True)
    instrument()
    sys.excepthook = log_uncaught
