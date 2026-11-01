from __future__ import annotations

from dataclasses import dataclass, field
import json
import threading
from typing import Any

import pytest

from power_desk_services import iris
from power_desk_services.runtime import Health


@dataclass
class Message:
    subject: str | None
    payload: bytes
    message_id: str = "m"

    @property
    def body(self) -> list[bytes]:  # Service Bus yields a data body in sections
        return [self.payload[:5], self.payload[5:]]


@dataclass
class FakeReceiver:
    """Hands out `batches` one receive at a time, then sets `stop`."""

    batches: list[list[Message]]
    stop: threading.Event
    completed: list[Message] = field(default_factory=list)
    dead_lettered: list[Message] = field(default_factory=list)

    def receive_messages(self, max_message_count: int | None = 1, max_wait_time: float | None = None) -> list[Any]:
        if not self.batches:
            self.stop.set()
            return []
        return self.batches.pop(0)

    def complete_message(self, message: Any) -> None:
        self.completed.append(message)

    def dead_letter_message(self, message: Any, reason: str | None = None, error_description: str | None = None):
        self.dead_lettered.append(message)


@dataclass
class FakeLanding:
    loads: list[dict[str, list[dict[str, Any]]]] = field(default_factory=list)
    fail: bool = False

    def land(self, rows: Any) -> None:
        if self.fail:
            raise OSError("bucket unavailable")
        self.loads.append({table: list(items) for table, items in rows.items()})


def message(subject: str | None, payload: Any) -> Message:
    return Message(subject, json.dumps(payload).encode())


CONFIG = iris.IrisConfig(client_id="id", client_secret="secret", queue_name="q", max_messages=2, max_seconds=60)


def consume(receiver: FakeReceiver, landing: FakeLanding) -> None:
    iris.consume(receiver, landing, CONFIG, Health(stale_after_seconds=60), receiver.stop)  # pyright: ignore[reportArgumentType]


def test_parse_keeps_records_as_published() -> None:
    assert iris.parse("FUELINST", b'[{"fuelType": "WIND"}]') == ("fuelinst", [{"fuelType": "WIND"}])
    assert iris.parse("SYSWARN", b'{"warningText": "x"}') == ("syswarn", [{"warningText": "x"}])


@pytest.mark.parametrize(
    ("subject", "body"), [(None, b"[]"), ("BOALF", b"not json"), ("BOALF", b"[1, 2]"), ("BOALF", b"\xff")]
)
def test_parse_rejects_messages_without_records(subject: str | None, body: bytes) -> None:
    with pytest.raises(ValueError):
        iris.parse(subject, body)


def test_consume_lands_full_batches_then_completes_them() -> None:
    first, second, third = (message("BOALF", [{"id": n}]) for n in range(3))
    receiver = FakeReceiver([[first, second], [third]], threading.Event())
    landing = FakeLanding()

    consume(receiver, landing)

    # the batch is full at 2 messages; the third is landed on stop
    assert landing.loads == [{"boalf": [{"id": 0}, {"id": 1}]}, {"boalf": [{"id": 2}]}]
    assert receiver.completed == [first, second, third]


def test_consume_dead_letters_unparseable_messages() -> None:
    good, bad = message("FUELINST", [{"fuelType": "WIND"}]), Message("FUELINST", b"<html>")
    receiver = FakeReceiver([[bad, good]], threading.Event())

    consume(receiver, FakeLanding())

    assert receiver.dead_lettered == [bad]
    assert receiver.completed == [good]


def test_consume_completes_nothing_when_landing_fails() -> None:
    receiver = FakeReceiver([[message("BOALF", [{"id": 1}]), message("BOALF", [{"id": 2}])]], threading.Event())

    with pytest.raises(OSError):
        consume(receiver, FakeLanding(fail=True))

    assert receiver.completed == []
