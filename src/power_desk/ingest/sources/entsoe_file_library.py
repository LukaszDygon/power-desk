"""ENTSO-E Transparency Platform File Library: listing and downloading exports.

Exports are tab-separated files under `TP_export/<folder>/`, downloaded zip-compressed and written
to disk as published (streamed, so memory does not grow with the file). The
client logs in with a Transparency Platform account, resolved by dlt on first use from
`sources.entsoe.credentials.{user,password}` (e.g. `SOURCES__ENTSOE__CREDENTIALS__USER`), and
renews its token before it expires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re
import shutil
import time
from typing import Any
import zipfile

import dlt
from dlt.sources.helpers import requests

from power_desk.ingest.http import USER_AGENT
from power_desk.ingest.windows import DateRange

TOKEN_URL = "https://keycloak.tp.entsoe.eu/realms/tp/protocol/openid-connect/token"
CLIENT_ID = "tp-fms-public"
API_URL = "https://fms.tp.entsoe.eu"
ROOT = "/TP_export/"
TOKEN_RENEWAL_MARGIN_SECONDS = 30  # renew this long before the token expires
LIST_PAGE_SIZE = 500
CHUNK_BYTES = 1 << 20
MONTHLY_EXPORT = re.compile(r"^(\d{4})_(\d{2})_")


@dataclass(frozen=True)
class ExportFile:
    """A monthly export; the publisher re-exports it (new `last_updated`) while its month's data changes."""

    name: str
    month: DateRange
    last_updated: str
    size: int | None = None


def export_month(name: str) -> DateRange | None:
    """The calendar month a `<YYYY>_<MM>_...` export covers."""
    match = MONTHLY_EXPORT.match(name)
    if not match:
        return None
    first = date(int(match[1]), int(match[2]), 1)
    return DateRange(first, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1))


def export_file(item: dict[str, Any]) -> ExportFile | None:
    """A listed folder item as a monthly export; None for sub-folders and other files (e.g. export logs)."""
    month = export_month(item["name"]) if item.get("type") != "Folder" else None
    if month is None:
        return None
    return ExportFile(item["name"], month, item.get("lastUpdatedTimestamp") or "", item.get("size"))


class FileLibraryClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at = 0.0

    def list_folder(self, folder: str) -> list[ExportFile]:
        """The monthly exports of a folder."""
        items: list[dict[str, Any]] = []
        while True:
            page = self._post(
                "listFolder",
                timeout=60,
                json={
                    "path": f"{ROOT}{folder}/",
                    "sorterList": [{"key": "periodCovered.from", "ascending": True}],
                    "pageInfo": {"pageIndex": len(items) // LIST_PAGE_SIZE, "pageSize": LIST_PAGE_SIZE},
                },
            ).json()
            items += page.get("contentItemList", [])
            if not page.get("contentItemList") or len(items) >= page["pageInfo"]["total"]:
                return [file for item in items if (file := export_file(item))]

    def download(self, folder: str, filename: str, target: Path) -> Path:
        """The export written to `target`, as published."""
        response = self._post(
            "downloadFileContent",
            timeout=(15, 120),
            stream=True,
            json={
                "folder": f"{ROOT}{folder}/",
                "filename": filename,
                "downloadAsZip": True,
                "topLevelFolder": ROOT.strip("/"),
            },
        )
        zipped = target.with_name(f"{target.name}.zip")
        with zipped.open("wb") as file:
            for chunk in response.iter_content(CHUNK_BYTES):
                file.write(chunk)
        with (
            zipfile.ZipFile(zipped) as archive,
            archive.open(archive.namelist()[0]) as export,
            target.open("wb") as out,
        ):
            shutil.copyfileobj(export, out, CHUNK_BYTES)
        zipped.unlink()
        return target

    def _post(self, endpoint: str, **kwargs: Any) -> requests.Response:
        response = requests.post(f"{API_URL}/{endpoint}", headers=self._headers(), **kwargs)
        response.raise_for_status()
        return response

    def _headers(self) -> dict[str, str]:
        if time.monotonic() >= self._expires_at:
            response = requests.post(
                TOKEN_URL,
                timeout=30,
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "password",
                    "username": dlt.secrets["sources.entsoe.credentials.user"],
                    "password": dlt.secrets["sources.entsoe.credentials.password"],
                },
            )
            response.raise_for_status()
            token = response.json()
            self._token = token["access_token"]
            self._expires_at = time.monotonic() + token["expires_in"] - TOKEN_RENEWAL_MARGIN_SECONDS
        return {"Authorization": f"Bearer {self._token}", "User-Agent": USER_AGENT}
