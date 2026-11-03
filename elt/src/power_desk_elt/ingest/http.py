"""HTTP access to publishers, with dlt's retrying client (429, 5xx and connection errors)."""

from __future__ import annotations

from typing import Any

from dlt.sources.helpers import requests
from requests import HTTPError

USER_AGENT = "PowerDesk/1.0"


def fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    response = requests.get(
        url, params=params, timeout=30, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    response.raise_for_status()
    return response.json()


def fetch_text(url: str) -> str:
    response = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def fetch_if_changed(
    url: str, etag: str | None = None, encoding: str = "utf-8-sig"
) -> tuple[str | None, dict[str, str]]:
    """A published file's text, or None while its ETag matches `etag`; plus its validators."""
    headers = {"User-Agent": USER_AGENT, **({"If-None-Match": etag} if etag else {})}
    response = requests.get(url, headers=headers, timeout=120)
    if response.status_code == 304:
        return None, {"etag": etag or ""}
    response.raise_for_status()
    validators = {"etag": response.headers.get("ETag", ""), "last_modified": response.headers.get("Last-Modified", "")}
    return response.content.decode(encoding), validators


def fetch_bytes(url: str, byte_range: tuple[int, int] | None = None) -> bytes | None:
    """A published file, or its bytes `start`..`end` inclusive; None while it is not published (404)."""
    headers = {"User-Agent": USER_AGENT, **({"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {})}
    try:  # dlt's client raises on 4xx itself
        response = requests.get(url, headers=headers, timeout=120)
        response.raise_for_status()
    except HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return None
        raise
    return response.content
