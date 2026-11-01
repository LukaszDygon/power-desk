from __future__ import annotations

from collections.abc import Iterator
import json
import logging
from pathlib import Path
import sys
from typing import Any

import dlt
import pytest

import power_desk_logging
from power_desk_logging import Formatter, log_context
from power_desk_logging.context import bound

logger = logging.getLogger("power_desk.test")


class Formatted(logging.Handler):
    """Formats records as they are logged, as a real handler does, while bound attributes are in effect."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(Formatter("test", json_format=True))
        self.entries: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.entries.append(json.loads(self.format(record)))

    def events(self, name: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e.get("event_name") == name]


@pytest.fixture
def formatted() -> Iterator[Formatted]:
    handler = Formatted()
    root = logging.getLogger()
    root.addHandler(handler)
    power_desk_logging.instrument()
    yield handler
    root.removeHandler(handler)


def record(message: str = "landed %s", **extra: object) -> logging.LogRecord:
    made = logging.LogRecord("power_desk.test", logging.INFO, "/src/iris.py", 7, message, ("x",), None, func="flush")
    made.__dict__.update(extra)
    return made


def test_json_record_follows_the_opentelemetry_log_data_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWER_DESK_ENV", "prod")
    entry = json.loads(
        Formatter("iris", json_format=True).format(record(event_name="dlt.load", **{"dlt.load_id": "1"}))
    )

    assert entry["timestamp"].endswith("+00:00")
    assert (entry["severity_text"], entry["severity_number"], entry["body"]) == ("INFO", 9, "landed x")
    assert (entry["event_name"], entry["scope_name"]) == ("dlt.load", "power_desk.test")
    assert entry["resource"].items() >= {"service.name": "iris", "deployment.environment.name": "prod"}.items()
    assert {"host.name", "process.pid"} <= entry["resource"].keys()
    assert entry["attributes"] == {
        "dlt.load_id": "1",
        "code.function.name": "flush",
        "code.file.path": "/src/iris.py",
        "code.line.number": 7,
    }


def test_text_line_carries_event_and_attributes_but_not_the_call_site() -> None:
    line = Formatter("backfill", json_format=False).format(record(event_name="dlt.load", **{"dlt.load_id": "1"}))

    assert line.endswith("INFO power_desk.test [dlt.load]: landed x dlt.load_id=1")


def test_bound_attributes_enrich_every_record_in_the_block(formatted: Formatted) -> None:
    with log_context({"messaging.destination.name": "q"}):
        with log_context({"dlt.load_id": "1"}):
            logger.info("inner")
        logger.info("outer", extra={"messaging.message.id": "m"})
    logger.info("after")

    inner, outer, after = (e.get("attributes", {}) for e in formatted.entries)
    assert inner.items() >= {"messaging.destination.name": "q", "dlt.load_id": "1"}.items()
    assert outer.items() >= {"messaging.destination.name": "q", "messaging.message.id": "m"}.items()
    assert "dlt.load_id" not in outer and "messaging.destination.name" not in after


def test_dagster_records_carry_the_run_and_the_original_message() -> None:
    meta: dict[str, object] = {"orig_message": "landed x", "run_id": "r-1", "job_name": "ingest", "step_key": "bmrs"}
    meta["dagster_event"] = None

    entry = json.loads(
        Formatter("orchestrator", json_format=True).format(record("ingest - r-1 - x", dagster_meta=meta))
    )

    assert entry["body"] == "landed x"
    assert entry["attributes"].items() >= {"dagster.run_id": "r-1", "dagster.step_key": "bmrs"}.items()


def test_exceptions_use_the_opentelemetry_attributes() -> None:
    try:
        raise OSError("bucket unavailable")
    except OSError:
        failed = record(exc_info=sys.exc_info())

    attributes = json.loads(Formatter("iris", json_format=True).format(failed))["attributes"]

    assert (attributes["exception.type"], attributes["exception.message"]) == ("OSError", "bucket unavailable")
    assert "Traceback" in attributes["exception.stacktrace"]


@pytest.fixture
def pipeline(tmp_path: Path) -> dlt.Pipeline:
    return dlt.pipeline(
        "probe",
        destination=dlt.destinations.filesystem(bucket_url=(tmp_path / "landing").as_posix()),
        dataset_name="probe",
        pipelines_dir=str(tmp_path / "pipelines"),
    )


def test_every_dlt_run_is_enriched_and_logs_its_loads(formatted: Formatted, pipeline: dlt.Pipeline) -> None:
    @dlt.resource(name="t1")
    def rows() -> Iterator[dict[str, int]]:
        logger.info("fetching")
        yield from ({"a": 1}, {"a": 2})

    pipeline.run([rows(), dlt.resource([{"b": 1}], name="t2")])

    fetching = next(e for e in formatted.entries if e["body"] == "fetching")["attributes"]
    assert fetching.items() >= {"dlt.pipeline_name": "probe", "dlt.step": "extract"}.items()
    (load,) = formatted.events("dlt.load")
    assert load["attributes"]["dlt.load_id"] == pipeline.last_trace.last_load_info.loads_ids[0]  # pyright: ignore[reportOptionalMemberAccess]
    assert load["attributes"]["dlt.row_counts"] == {"t1": 2, "t2": 1}
    assert load["attributes"]["dlt.step"] == "load"
    assert not bound()  # nothing leaks past the run


def test_dlt_logs_reach_our_handlers(formatted: Formatted, pipeline: dlt.Pipeline) -> None:
    pipeline.run([{"a": 1}], table_name="t")  # dlt (re)initialises its logger

    logging.getLogger("dlt").warning("from dlt")

    assert [e["body"] for e in formatted.entries if e["scope_name"] == "dlt"] == ["from dlt"]


def test_uncaught_exceptions_are_records(caplog: pytest.LogCaptureFixture) -> None:
    power_desk_logging.log_uncaught(OSError, OSError("bucket unavailable"), None)

    (logged,) = caplog.records
    assert (logged.levelname, logged.getMessage()) == ("CRITICAL", "stopped on OSError: bucket unavailable")
