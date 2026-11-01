"""ENTSO-E Transparency Platform subscriptions: data items the platform pushes as they are published.

The platform calls our web service channel (`POST /subscriptions`, SOAP 1.2, `iec62325.py`) with each
published document. Every document is landed (`entsoe_subscription/<document kind>/`, e.g.
`publication_market_document`) with its header fields and the XML as pushed, before the call is answered with
an acknowledgement. Failures answer a SOAP fault (HTTP 500), so the platform retries; a channel that does not
acknowledge is disabled after 100 attempts, and its data is held for 2 days.

Endpoint requirements (Subscription Service Introduction Guide for Data Consumers):
- HTTPS (TLS 1.2+) with a certificate from a CA the platform trusts, terminated in front of the service;
- reachable from the platform's addresses, 4.185.182.62 and 4.182.105.72;
- the channel check is a plain POST that must not get HTTP 400 (a malformed request gets a 500 fault here).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
import uvicorn

from power_desk_services import iec62325, settings
from power_desk_services.landing import Landing

logger = logging.getLogger(__name__)

SOURCE = "entsoe_subscription"


def rows(request: iec62325.Request) -> dict[str, list[dict[str, Any]]]:
    """One row per document, in the table of its kind: header fields and the document."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for doc in request.documents:
        tables.setdefault(doc.kind, []).append(
            {name: doc.get(name) or None for name in ("mRID", "revisionNumber", "type", "createdDateTime")}
            | {"document": doc.xml}
        )
    return tables


def create_app(landing: Landing | None = None) -> FastAPI:
    app = FastAPI(openapi_url=None)  # no schema or docs routes on a public endpoint
    landing = landing or Landing(SOURCE)

    def soap(content: bytes, status_code: int = 200) -> Response:
        return Response(content, status_code=status_code, media_type=iec62325.CONTENT_TYPE)

    @app.post("/subscriptions")
    async def receive(http_request: Request) -> Response:
        body = await http_request.body()
        try:
            request = iec62325.parse_request(body)
        except Exception as error:  # malformed XML, base64 or archive: the sender's fault, never HTTP 400
            logger.warning("rejected %d-byte request: %s", len(body), error)
            return soap(iec62325.fault(f"malformed request: {error}", code="Sender"), 500)
        try:
            await run_in_threadpool(landing.land, rows(request))
        except Exception:
            logger.exception("landing failed")
            return soap(iec62325.fault("could not store the documents; retry"), 500)
        logger.info("landed %s", ", ".join(f"{d.kind} {d.get('mRID')}" for d in request.documents))
        return soap(iec62325.response(request))

    @app.get("/healthz")
    def health() -> Response:
        return Response("ok", media_type="text/plain")

    return app


class SkipProbes(logging.Filter):
    """Keeps the cluster's health probes out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return '"GET /healthz ' not in record.getMessage()


def main() -> None:
    logging.getLogger("uvicorn.access").addFilter(SkipProbes())
    logger.info("receiving ENTSO-E subscriptions on :%d into %s", settings.port(), settings.landing_url())
    uvicorn.run(create_app(), host="0.0.0.0", port=settings.port(), log_config=None)
