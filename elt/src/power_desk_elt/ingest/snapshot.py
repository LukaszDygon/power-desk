"""Snapshots: whole reference files re-read on each run and loaded as scd2 versions.

A snapshot's resource re-reads the published file and loads it with dlt's `scd2` merge strategy and no
`merge_key`, so changed and withdrawn rows keep their history (`_dlt_valid_from` / `_dlt_valid_to`). A
file whose ETag / content hash is unchanged since its last load is skipped, and a skipped run changes
nothing. The file's address, validators and hash are kept in the resource state (`source_file`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import hashlib
import logging
from typing import Any

import dlt
from dlt.sources import DltResource

from power_desk_elt.ingest import http
from power_desk_elt.ingest.spec import SCD2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    resource: str
    url: str | Callable[[], str]  # or a lookup of the current address, for files published at a new one
    parse: Callable[[str], list[dict[str, Any]]]
    natural_key: tuple[str, ...]  # published column names; empty where the publisher documents none
    encoding: str = "utf-8-sig"

    def address(self) -> str:
        return self.url if isinstance(self.url, str) else self.url()


def changed_rows(snapshot: Snapshot) -> Iterator[list[dict[str, Any]]]:
    """All rows of the published file, unless it is unchanged since its last load."""
    state = dlt.current.resource_state()
    previous = state.get("source_file", {})
    url = snapshot.address()
    etag = previous.get("etag") if previous.get("url", url) == url else None
    text, validators = http.fetch_if_changed(url, etag=etag or None, encoding=snapshot.encoding)
    digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else previous.get("sha256")
    new_text = text if digest != previous.get("sha256") else None
    state["source_file"] = {
        "url": url,
        "etag": validators.get("etag") or etag,
        "last_modified": validators.get("last_modified") or previous.get("last_modified"),
        "sha256": digest,
        "changed": new_text is not None,
    }
    if new_text is not None:
        rows = snapshot.parse(new_text)
        logger.info("%s: %d rows from %s", snapshot.resource, len(rows), url)
        yield rows


def snapshot_resource(snapshot: Snapshot) -> DltResource:
    resource = dlt.resource(
        changed_rows(snapshot), name=snapshot.resource, write_disposition=SCD2, file_format="parquet"
    )
    if snapshot.natural_key:
        resource.apply_hints(primary_key=list(snapshot.natural_key))
    return resource
