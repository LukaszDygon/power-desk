"""IEC 62325-504 web service messages, as the ENTSO-E Transparency Platform pushes subscribed data.

A push is a SOAP 1.2 call of the `request` operation: an IEC 61968-100 `RequestMessage` whose `Payload`
holds market documents, inline or base64 in `Compressed` (zip or gzip). The answer is a `ResponseMessage`
with `Reply/Result` OK and an `Acknowledgement_MarketDocument` (IEC 62325-451-1) per document.
References: ENTSO-E Subscription Service Introduction Guide for Data Consumers; the sample subscriber
https://gitlab.entsoe.eu/transparency/subscriptions (WSDL `urn-iec62325-504-wss-1-0.wsdl`).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import io
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring
import zipfile

from defusedxml.ElementTree import fromstring

SOAP = "http://www.w3.org/2003/05/soap-envelope"
MSG = "http://iec.ch/TC57/2011/schema/message"
DSIG = "http://www.w3.org/2000/09/xmldsig#"
ACK = "urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
CONTENT_TYPE = "application/soap+xml; charset=utf-8"

# fallbacks when a document lacks its parties (Guide, Appendix: Elements of Request)
PLATFORM_EIC, PLATFORM_ROLE = "10X1001A1001A450", "A32"  # ENTSO-E, market information aggregator
CONSUMER_EIC, CONSUMER_ROLE = "1234567890123456", "A33"  # no organisation, information receiver
ACCEPTED = "A01"  # Reason code: message fully accepted

for _prefix, _uri in (("env", SOAP), ("msg", MSG), ("ds", DSIG)):
    register_namespace(_prefix, _uri)


@dataclass(frozen=True)
class MarketDocument:
    """A document as pushed: its root element name, header fields, and the XML.

    Compressed documents keep their bytes as delivered; inline ones are re-serialised from the envelope,
    the same XML with generated namespace prefixes (`ns0:`).
    """

    kind: str  # root element, e.g. `Publication_MarketDocument`
    fields: dict[str, str]  # the root's simple children, e.g. `mRID`, `type`, `createdDateTime`
    xml: str

    def get(self, name: str, default: str = "") -> str:
        return self.fields.get(name) or default


@dataclass(frozen=True)
class Request:
    context: str | None
    signature: Element | None
    documents: list[MarketDocument]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def parse_request(body: bytes) -> Request:
    """The market documents of a pushed SOAP envelope; ValueError if it is not a `RequestMessage`."""
    envelope = fromstring(body)
    message = envelope.find(f"{{{SOAP}}}Body/{{{MSG}}}RequestMessage")
    if message is None:
        raise ValueError("no SOAP 1.2 Body/RequestMessage")
    payload = message.find(f"{{{MSG}}}Payload")
    documents: list[MarketDocument] = []
    if payload is not None:
        compressed = payload.find(f"{{{MSG}}}Compressed")
        if compressed is not None:
            for xml in decompress(base64.b64decode(compressed.text or "", validate=True)):
                text = xml.decode("utf-8-sig")
                documents.append(document(fromstring(xml), text))
        else:
            documents = [
                document(child, tostring(child, encoding="unicode")) for child in payload if namespace(child.tag) != MSG
            ]
    if not documents:
        raise ValueError("RequestMessage has no market document in its Payload")
    return Request(
        context=message.findtext(f"{{{MSG}}}Header/{{{MSG}}}Context"),
        signature=message.find(f".//{{{DSIG}}}Signature"),
        documents=documents,
    )


def decompress(data: bytes) -> list[bytes]:
    """The XML files of a `Compressed` payload: a zip archive, gzip, or plain XML."""
    if data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return [archive.read(name) for name in archive.namelist() if not name.endswith("/")]
    if data.startswith(b"\x1f\x8b"):
        return [gzip.decompress(data)]
    return [data]


def document(root: Element, xml: str) -> MarketDocument:
    fields = {local_name(child.tag): (child.text or "").strip() for child in root if len(child) == 0}
    return MarketDocument(kind=local_name(root.tag), fields=fields, xml=xml)


def timestamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def acknowledgement(doc: MarketDocument, now: datetime) -> Element:
    """An `Acknowledgement_MarketDocument` accepting `doc`: sender and receiver swapped, reason A01."""
    ack = Element(f"{{{ACK}}}Acknowledgement_MarketDocument")

    def add(name: str, text: str, **attributes: str) -> None:
        SubElement(ack, f"{{{ACK}}}{name}", attributes).text = text

    add("mRID", f"ACK_{doc.get('mRID')}"[:60])  # ID_String: at most 60 characters
    add("createdDateTime", timestamp(now))
    for party, other, eic, role in (
        ("sender", "receiver", CONSUMER_EIC, CONSUMER_ROLE),
        ("receiver", "sender", PLATFORM_EIC, PLATFORM_ROLE),
    ):
        add(f"{party}_MarketParticipant.mRID", doc.get(f"{other}_MarketParticipant.mRID", eic), codingScheme="A01")
        add(f"{party}_MarketParticipant.marketRole.type", doc.get(f"{other}_MarketParticipant.marketRole.type", role))
    for name in ("mRID", "revisionNumber", "type", "createdDateTime"):
        if value := doc.get(name):
            add(f"received_MarketDocument.{name}", value)
    reason = SubElement(ack, f"{{{ACK}}}Reason")
    SubElement(reason, f"{{{ACK}}}code").text = ACCEPTED
    return ack


def response(request: Request, now: datetime | None = None) -> bytes:
    """The SOAP envelope acknowledging every document of `request`.

    Like ENTSO-E's sample subscriber, the header carries the request's `ds:Signature`, if any.
    """
    now = now or datetime.now(UTC)
    envelope = Element(f"{{{SOAP}}}Envelope")
    message = SubElement(SubElement(envelope, f"{{{SOAP}}}Body"), f"{{{MSG}}}ResponseMessage")
    header = SubElement(message, f"{{{MSG}}}Header")
    for name, text in (
        ("Verb", "reply"),
        ("Noun", "Acknowledgement_MarketDocument"),
        ("Context", request.context or "PRODUCTION"),
        ("Timestamp", timestamp(now)),
        ("AckRequired", "true"),
    ):
        SubElement(header, f"{{{MSG}}}{name}").text = text
    if request.signature is not None:
        header.append(request.signature)
    SubElement(SubElement(message, f"{{{MSG}}}Reply"), f"{{{MSG}}}Result").text = "OK"
    payload = SubElement(message, f"{{{MSG}}}Payload")
    payload.extend(acknowledgement(doc, now) for doc in request.documents)
    SubElement(payload, f"{{{MSG}}}Format").text = "XML"
    return tostring(envelope, encoding="utf-8", xml_declaration=True)


def fault(reason: str, code: str = "Receiver") -> bytes:
    """A SOAP 1.2 fault; `code` is `Sender` for a malformed request, `Receiver` for our failure."""
    envelope = Element(f"{{{SOAP}}}Envelope")
    body = SubElement(SubElement(envelope, f"{{{SOAP}}}Body"), f"{{{SOAP}}}Fault")
    SubElement(SubElement(body, f"{{{SOAP}}}Code"), f"{{{SOAP}}}Value").text = f"env:{code}"
    SubElement(SubElement(body, f"{{{SOAP}}}Reason"), f"{{{SOAP}}}Text", {XML_LANG: "en"}).text = reason
    return tostring(envelope, encoding="utf-8", xml_declaration=True)
