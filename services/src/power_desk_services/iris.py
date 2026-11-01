"""Elexon IRIS (Insights Real-time Information Service): BMRS datasets pushed to a queue, landed as they arrive.

IRIS is an Azure Service Bus queue per client (https://bmrs.elexon.co.uk/iris, client samples:
https://github.com/elexon-data/iris-clients). Each message's subject is the dataset code (e.g. `BOALF`) and
its body the dataset's records as JSON, in the Insights API format. Messages expire after 3 days in the queue
(gaps are filled from the API); the queue allows one connection, so the service runs as one replica.

Messages are received in peek-lock and buffered until `max_messages` or `max_seconds`, then landed in one dlt
load (a table per dataset, `iris/<dataset>/`) and completed. A crash before completing re-delivers them.
Messages that are not JSON records are dead-lettered.

Settings are dlt config and secrets (from the IRIS page of the Insights Solution):

| Key | Env | |
|---|---|---|
| `sources.iris.credentials.client_id` | `SOURCES__IRIS__CREDENTIALS__CLIENT_ID` | required |
| `sources.iris.credentials.client_secret` | `SOURCES__IRIS__CREDENTIALS__CLIENT_SECRET` | required; valid 2 years |
| `sources.iris.queue_name` | `SOURCES__IRIS__QUEUE_NAME` | required |
| `sources.iris.max_messages` | `SOURCES__IRIS__MAX_MESSAGES` | default 500 |
| `sources.iris.max_seconds` | `SOURCES__IRIS__MAX_SECONDS` | default 30 |
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import logging
import threading
import time
from typing import Any, Protocol

from azure.identity import ClientSecretCredential
from azure.servicebus import AutoLockRenewer, ServiceBusClient, ServiceBusReceivedMessage
import dlt

from power_desk_logging import log_context
from power_desk_services import settings
from power_desk_services.landing import Landing
from power_desk_services.runtime import Health, serve_health, stop_on_signals

logger = logging.getLogger(__name__)

SOURCE = "iris"
# Elexon's Entra tenant and Service Bus namespace (elexon-data/iris-clients README)
TENANT_ID = "4203b7a0-7773-4de5-b830-8b263a20426e"
NAMESPACE = "elexon-insights-iris.servicebus.windows.net"
RECEIVE_WAIT_SECONDS = 5


@dataclass(frozen=True)
class IrisConfig:
    client_id: str
    client_secret: str
    queue_name: str
    max_messages: int = 500
    max_seconds: float = 30.0

    @classmethod
    def from_dlt(cls) -> IrisConfig:
        """Credentials and queue from dlt secrets (missing ones raise, naming the variable); limits from dlt config."""
        return cls(
            client_id=dlt.secrets["sources.iris.credentials.client_id"],
            client_secret=dlt.secrets["sources.iris.credentials.client_secret"],
            queue_name=dlt.secrets["sources.iris.queue_name"],
            max_messages=dlt.config.get("sources.iris.max_messages", int) or cls.max_messages,
            max_seconds=dlt.config.get("sources.iris.max_seconds", float) or cls.max_seconds,
        )


def parse(subject: str | None, body: bytes) -> tuple[str, list[dict[str, Any]]]:
    """The table (dataset code, lower case) and records of a message; ValueError if it holds no records."""
    if not subject:
        raise ValueError("message has no subject (dataset code)")
    payload = json.loads(body)
    records = payload if isinstance(payload, list) else [payload]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"{subject}: body is not a JSON record or list of records")
    return subject.lower(), records


class Receiver(Protocol):
    """The part of azure's `ServiceBusReceiver` the service uses."""

    def receive_messages(
        self, max_message_count: int | None = 1, max_wait_time: float | None = None
    ) -> list[ServiceBusReceivedMessage]: ...

    def complete_message(self, message: ServiceBusReceivedMessage) -> None: ...

    def dead_letter_message(
        self, message: ServiceBusReceivedMessage, reason: str | None = None, error_description: str | None = None
    ) -> None: ...


@dataclass
class Batch:
    messages: list[ServiceBusReceivedMessage] = field(default_factory=list)
    rows: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    started: float = 0.0

    def add(self, message: ServiceBusReceivedMessage, table: str, records: list[dict[str, Any]]) -> None:
        if not self.messages:
            self.started = time.monotonic()
        self.messages.append(message)
        self.rows[table].extend(records)

    def due(self, max_messages: int, max_seconds: float) -> bool:
        return len(self.messages) >= max_messages or (
            bool(self.messages) and time.monotonic() - self.started >= max_seconds
        )


def flush(batch: Batch, receiver: Receiver, landing: Landing) -> None:
    """Land the batch, then complete its messages."""
    if not batch.messages:
        return
    landing.land(batch.rows)
    for message in batch.messages:
        receiver.complete_message(message)
    count = len(batch.messages)
    logger.info("completed %d messages", count, extra={"messaging.batch.message_count": count})


def consume(receiver: Receiver, landing: Landing, config: IrisConfig, health: Health, stop: threading.Event) -> None:
    """Receive, land and complete messages until `stop` is set; the batch in hand is landed before returning."""
    batch = Batch()
    while not stop.is_set():
        wanted = config.max_messages - len(batch.messages)
        for message in receiver.receive_messages(max_message_count=wanted, max_wait_time=RECEIVE_WAIT_SECONDS):
            try:
                table, records = parse(message.subject, b"".join(message.body))
            except ValueError as error:  # includes JSON and UTF-8 decoding errors
                logger.error(
                    "dead-lettering message %s: %s",
                    message.message_id,
                    error,
                    extra={"messaging.message.id": message.message_id, "messaging.operation.name": "dead_letter"},
                )
                receiver.dead_letter_message(message, reason="unparseable", error_description=str(error)[:1024])
                continue
            batch.add(message, table, records)
        if batch.due(config.max_messages, config.max_seconds):
            flush(batch, receiver, landing)
            batch = Batch()
        health.beat()
    flush(batch, receiver, landing)


def main() -> None:
    config = IrisConfig.from_dlt()
    health = Health(stale_after_seconds=config.max_seconds + 10 * RECEIVE_WAIT_SECONDS)
    serve_health(health, settings.port())
    stop = stop_on_signals()
    landing = Landing(SOURCE)
    credential = ClientSecretCredential(TENANT_ID, config.client_id, config.client_secret)
    with (
        # every record names the queue (OpenTelemetry messaging attributes)
        log_context({"messaging.system": "servicebus", "messaging.destination.name": config.queue_name}),
        # renews the locks of messages held in a batch until they are completed
        AutoLockRenewer(max_lock_renewal_duration=config.max_seconds + 300) as renewer,
        ServiceBusClient(NAMESPACE, credential) as client,
        client.get_queue_receiver(config.queue_name, auto_lock_renewer=renewer) as receiver,
    ):
        logger.info("receiving from IRIS queue %s into %s", config.queue_name, settings.landing_url())
        consume(receiver, landing, config, health, stop)
