"""The record of the log standard: the OpenTelemetry log data model, as JSON or as a line of text."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
import os
import socket
from typing import Any

from power_desk_logging.context import bound

NAMESPACE = "power-desk"
EVENT_NAME = "event_name"
# OpenTelemetry severity numbers of the standard levels
SEVERITY_NUMBER = {logging.DEBUG: 5, logging.INFO: 9, logging.WARNING: 13, logging.ERROR: 17, logging.CRITICAL: 21}
DAGSTER_META = "dagster_meta"  # set by Dagster on the records it handles
CALL_SITE = "code."  # attributes left out of text lines, which name the logger already


class Formatter(logging.Formatter):
    """`json_format` defaults to `POWER_DESK_LOG_FORMAT=json`; otherwise a line of text for people."""

    def __init__(self, service: str, json_format: bool | None = None) -> None:
        super().__init__()
        self.resource = {
            "service.namespace": NAMESPACE,
            "service.name": service,
            "deployment.environment.name": os.environ.get("POWER_DESK_ENV", "dev"),
            "host.name": socket.gethostname(),
            "process.pid": os.getpid(),
        }
        self.json = os.environ.get("POWER_DESK_LOG_FORMAT") == "json" if json_format is None else json_format

    def format(self, record: logging.LogRecord) -> str:
        meta = getattr(record, DAGSTER_META, None)
        body = meta["orig_message"] if meta else record.getMessage()
        event_name = getattr(record, EVENT_NAME, None)
        found = attributes(record, self)
        if self.json:
            entry = {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
                "severity_text": record.levelname,
                "severity_number": SEVERITY_NUMBER.get(record.levelno, 0),
                "body": body,
                EVENT_NAME: event_name,
                "scope_name": record.name,
                "resource": self.resource,
                "attributes": found,
            }
            return json.dumps({key: value for key, value in entry.items() if value is not None}, default=str)
        stacktrace = found.pop("exception.stacktrace", None)
        pairs = "".join(f" {key}={value}" for key, value in found.items() if not key.startswith(CALL_SITE))
        event = f" [{event_name}]" if event_name else ""
        line = f"{self.formatTime(record)} {record.levelname} {record.name}{event}: {body}{pairs}"
        return f"{line}\n{stacktrace}" if stacktrace else line


def attributes(record: logging.LogRecord, formatter: logging.Formatter) -> dict[str, Any]:
    """Bound attributes, then the record's dotted `extra` keys, Dagster's run metadata, the call site and the
    exception, by their OpenTelemetry names."""
    found: dict[str, Any] = {**bound(), **{key: value for key, value in vars(record).items() if "." in key}}
    if meta := getattr(record, DAGSTER_META, None):
        event = meta.get("dagster_event")
        found |= {
            "dagster.run_id": meta.get("run_id"),
            "dagster.job_name": meta.get("job_name"),
            "dagster.step_key": meta.get("step_key"),
            "dagster.event_type": event.event_type_value if event else None,
        }
    found |= {
        "code.function.name": record.funcName,
        "code.file.path": record.pathname,
        "code.line.number": record.lineno,
    }
    if record.threadName != "MainThread":
        found["thread.name"] = record.threadName
    if record.exc_info and record.exc_info[0]:
        found |= {
            "exception.type": record.exc_info[0].__name__,
            "exception.message": str(record.exc_info[1]),
            "exception.stacktrace": formatter.formatException(record.exc_info),
        }
    return {key: value for key, value in found.items() if value is not None}
