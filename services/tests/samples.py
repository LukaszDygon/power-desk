"""Payloads as publishers push them, and where the landing zone puts them."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

PUBLICATION = """<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <mRID>c1b9f2a0e0d14c2b9d7c</mRID>
  <revisionNumber>1</revisionNumber>
  <type>A44</type>
  <sender_MarketParticipant.mRID codingScheme="A01">10X1001A1001A450</sender_MarketParticipant.mRID>
  <sender_MarketParticipant.marketRole.type>A32</sender_MarketParticipant.marketRole.type>
  <receiver_MarketParticipant.mRID codingScheme="A01">10X1001A1001A450</receiver_MarketParticipant.mRID>
  <receiver_MarketParticipant.marketRole.type>A33</receiver_MarketParticipant.marketRole.type>
  <createdDateTime>2026-10-30T12:00:00Z</createdDateTime>
  <TimeSeries><mRID>1</mRID><Period><Point><position>1</position><price.amount>81.5</price.amount></Point></Period></TimeSeries>
</Publication_MarketDocument>"""


def envelope(payload: str) -> bytes:
    """A pushed SOAP 1.2 `RequestMessage` with `payload` inside its `Payload`."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Body>
    <msg:RequestMessage xmlns:msg="http://iec.ch/TC57/2011/schema/message">
      <msg:Header>
        <msg:Verb>create</msg:Verb>
        <msg:Noun>Publication_MarketDocument</msg:Noun>
        <msg:Context>PRODUCTION</msg:Context>
      </msg:Header>
      <msg:Payload>{payload}</msg:Payload>
    </msg:RequestMessage>
  </env:Body>
</env:Envelope>""".encode()


def landed_files(landing_root: Path, table: str) -> list[Path]:
    """The files landed for `table` of the test source under `landing_root`."""
    return sorted((landing_root / "test_source" / table).glob("*.jsonl*"))


def landed_rows(landing_root: Path, table: str) -> list[dict[str, Any]]:
    rows = []
    for file in landed_files(landing_root, table):
        with gzip.open(file, "rt") as lines:
            rows.extend(json.loads(line) for line in lines)
    return rows
