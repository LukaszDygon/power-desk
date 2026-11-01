from __future__ import annotations

import base64
from datetime import UTC, datetime
import gzip
import io
from pathlib import Path
import zipfile

from defusedxml.ElementTree import fromstring
from fastapi.testclient import TestClient
import pytest
from samples import PUBLICATION, envelope, landed_rows

from power_desk_services import entsoe_subscription, iec62325
from power_desk_services.landing import Landing

MSG, ACK, SOAP = iec62325.MSG, iec62325.ACK, iec62325.SOAP


def zipped(*documents: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for n, doc in enumerate(documents):
            archive.writestr(f"doc_{n}.xml", doc)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "payload",
    [
        PUBLICATION,
        f"<msg:Compressed>{base64.b64encode(zipped(PUBLICATION)).decode()}</msg:Compressed><msg:Format>XML</msg:Format>",
        f"<msg:Compressed>{base64.b64encode(gzip.compress(PUBLICATION.encode())).decode()}</msg:Compressed>",
    ],
    ids=["inline", "zip", "gzip"],
)
def test_parse_request_finds_the_document(payload: str) -> None:
    request = iec62325.parse_request(envelope(payload))

    (doc,) = request.documents
    assert request.context == "PRODUCTION"
    assert doc.kind == "Publication_MarketDocument"
    assert doc.get("mRID") == "c1b9f2a0e0d14c2b9d7c"
    assert doc.get("type") == "A44"
    # the document is the same XML as pushed
    stored = fromstring(doc.xml)
    assert stored.tag == "{urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3}Publication_MarketDocument"
    assert [p.text for p in stored.iter() if p.tag.endswith("price.amount")] == ["81.5"]


@pytest.mark.parametrize("body", [b"", b"<a/>", envelope("")], ids=["empty", "not soap", "no document"])
def test_parse_request_rejects(body: bytes) -> None:
    with pytest.raises(Exception):  # noqa: B017 - XML or ValueError, both answered with a fault
        iec62325.parse_request(body)


def test_response_acknowledges_each_document() -> None:
    request = iec62325.parse_request(envelope(PUBLICATION))

    root = fromstring(iec62325.response(request, now=datetime(2026, 10, 31, 9, 30, tzinfo=UTC)))

    message = root.find(f"{{{SOAP}}}Body/{{{MSG}}}ResponseMessage")
    assert message is not None
    assert message.findtext(f"{{{MSG}}}Header/{{{MSG}}}Verb") == "reply"
    assert message.findtext(f"{{{MSG}}}Reply/{{{MSG}}}Result") == "OK"
    ack = message.find(f"{{{MSG}}}Payload/{{{ACK}}}Acknowledgement_MarketDocument")
    assert ack is not None
    fields = {child.tag.split("}")[1]: child.text for child in ack if len(child) == 0}
    assert fields == {
        "mRID": "ACK_c1b9f2a0e0d14c2b9d7c",
        "createdDateTime": "2026-10-31T09:30:00Z",
        "sender_MarketParticipant.mRID": "10X1001A1001A450",
        "sender_MarketParticipant.marketRole.type": "A33",
        "receiver_MarketParticipant.mRID": "10X1001A1001A450",
        "receiver_MarketParticipant.marketRole.type": "A32",
        "received_MarketDocument.mRID": "c1b9f2a0e0d14c2b9d7c",
        "received_MarketDocument.revisionNumber": "1",
        "received_MarketDocument.type": "A44",
        "received_MarketDocument.createdDateTime": "2026-10-30T12:00:00Z",
    }
    assert ack.findtext(f"{{{ACK}}}Reason/{{{ACK}}}code") == "A01"


def test_endpoint_lands_the_document_then_acknowledges(landing: Landing, landing_root: Path) -> None:
    client = TestClient(entsoe_subscription.create_app(landing))

    reply = client.post("/subscriptions", content=envelope(PUBLICATION))

    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("application/soap+xml")
    assert b"Acknowledgement_MarketDocument" in reply.content
    (row,) = landed_rows(landing_root, "publication_market_document")
    assert (row["m_rid"], row["type"], row["revision_number"]) == ("c1b9f2a0e0d14c2b9d7c", "A44", "1")
    assert "price.amount>81.5</" in row["document"]


def test_channel_check_post_is_not_answered_400(landing: Landing) -> None:
    reply = TestClient(entsoe_subscription.create_app(landing)).post("/subscriptions", content=b"")

    assert reply.status_code == 500
    assert b"env:Sender" in reply.content


def test_failed_landing_answers_a_fault_so_the_platform_retries() -> None:
    class Failing:
        def land(self, rows: object) -> None:
            raise OSError("bucket unavailable")

    client = TestClient(entsoe_subscription.create_app(Failing()))  # pyright: ignore[reportArgumentType]

    reply = client.post("/subscriptions", content=envelope(PUBLICATION))

    assert reply.status_code == 500
    assert b"env:Receiver" in reply.content
