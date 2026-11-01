"""Process concerns of a worker service: stopping on SIGTERM, and a liveness endpoint for the cluster's probes.

`/healthz` answers 200 while the worker's loop keeps calling `Health.beat`. HTTP services serve it themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import signal
import threading
import time

logger = logging.getLogger(__name__)


@dataclass
class Health:
    stale_after_seconds: float
    _last_beat: float = field(default_factory=time.monotonic)

    def beat(self) -> None:
        self._last_beat = time.monotonic()

    @property
    def alive(self) -> bool:
        return time.monotonic() - self._last_beat < self.stale_after_seconds


def serve_health(health: Health, port: int) -> None:
    """Serve `/healthz` on `port` from a daemon thread."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/healthz":
                self.send_error(404)
            elif health.alive:
                self.send_response(200)
                self.end_headers()
            else:
                self.send_error(503, "worker loop stalled")

        def log_message(self, format: str, *args: object) -> None:  # probes every few seconds: keep logs quiet
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="health", daemon=True).start()


def stop_on_signals() -> threading.Event:
    """An event set on SIGTERM (the cluster stopping the pod) or SIGINT."""
    stop = threading.Event()

    def handle(signum: int, _frame: object) -> None:
        logger.info("received %s, stopping", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    return stop
