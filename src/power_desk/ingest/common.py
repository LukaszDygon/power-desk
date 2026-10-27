"""Building blocks shared by every dlt source.

Contract for a source module (`ingest/<source>.py`):
- a `@dlt.source` whose resources each own one `dlt.sources.incremental` cursor;
- each resource plans its fetch with `incremental_window`, so open-ended runs resume
  from the cursor in steps of at most `max_days_per_run` new days, and bounded
  backfills (`end_value` set) leave both the cursor and the recorded window untouched;
- a module-level `SPEC = SourceSpec(...)`, registered in `ingest/pipelines.py`.
Raw payloads are yielded untouched; typing and conforming happen in dbt staging models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Iterator

import dlt
from dlt.sources import DltSource
from dlt.sources.helpers import requests

USER_AGENT = "PowerDesk/1.0 (Analyst Terminal)"


@dataclass(frozen=True)
class SourceSpec:
    """How the orchestrator and CLIs build and run one dlt source / pipeline."""

    name: str  # dlt pipeline name == dlt source/schema name
    build_source: Callable[..., DltSource]  # (initial_date, end_date, max_days_per_run) -> DltSource
    max_days_per_run: int = 7
    # Days added on each side of a requested date range, for sources whose local dates
    # are published across UTC day boundaries.
    window_padding_days: int = 0


def fetch_json(url: str, params: dict[str, Any] | None = None, timeout: int = 30, **headers: str) -> Any:
    """GET JSON with dlt's retrying requests client (retries 429/5xx and connection errors)."""
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers},
    )
    response.raise_for_status()
    return response.json()


def fetch_if_changed(url: str, etag: str | None = None, timeout: int = 120) -> tuple[str | None, dict[str, str]]:
    """GET a published file unless its ETag matches; returns (text or None if unchanged, validators).

    For snapshot-style reference files: the resource stores the returned validators in its
    state and skips the download (yields nothing) while the publisher's file is unchanged.
    """
    headers = {"User-Agent": USER_AGENT, **({"If-None-Match": etag} if etag else {})}
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code == 304:
        return None, {"etag": etag or ""}
    response.raise_for_status()
    validators = {"etag": response.headers.get("ETag", ""), "last_modified": response.headers.get("Last-Modified", "")}
    return response.content.decode("utf-8-sig"), validators


def to_date(value: Any) -> date:
    """Coerce a cursor value (date, datetime or ISO string) to a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def day_after(value: str) -> str:
    """Exclusive `end_value` for an inclusive end date."""
    return (to_date(value) + timedelta(days=1)).isoformat()


def plan_window(
    start_value: Any,
    end_value: Any | None,
    max_days_per_run: int,
    fetched_until: str | None = None,
    today: date | None = None,
) -> tuple[date, date, bool]:
    """Return the (first_day, last_day, capped) window an incremental run should fetch.

    Open-ended runs start at the later of the cursor's day and the last day fetched by
    the previous run (re-fetched to pick up late publications), then add at most
    `max_days_per_run` new days. Tracking `fetched_until` lets the window advance through
    periods where the API published nothing, which never move the cursor.
    `capped` is True when the run stopped short of today, i.e. more data is waiting.
    """
    today = today or datetime.now(UTC).date()
    first_day = to_date(start_value)
    if end_value is not None:
        # end_value is exclusive
        return first_day, to_date(end_value) - timedelta(days=1), False
    if fetched_until:
        first_day = max(first_day, date.fromisoformat(fetched_until))
    cap_day = first_day + timedelta(days=max_days_per_run)
    return first_day, min(today, cap_day), cap_day < today


def incremental_window(cursor: dlt.sources.incremental, max_days_per_run: int) -> tuple[date, date]:
    """Plan this run's window and record it in resource state.

    The recorded window (committed only with a successful load) drives the next run's
    start and is read by the orchestrator's catch-up sensor. Bounded backfills
    (`end_value` set) leave it untouched, like dlt leaves the cursor untouched.
    """
    if cursor.end_value is not None:
        first_day, last_day, _ = plan_window(cursor.start_value, cursor.end_value, max_days_per_run)
        return first_day, last_day
    state = dlt.current.resource_state()
    previous = state.get("last_window", {}).get("last_day")
    first_day, last_day, capped = plan_window(cursor.start_value, None, max_days_per_run, fetched_until=previous)
    state["last_window"] = {"first_day": first_day.isoformat(), "last_day": last_day.isoformat(), "capped": capped}
    return first_day, last_day


def iter_day_windows(first_day: date, last_day: date, step_days: int) -> Iterator[tuple[date, date]]:
    """Split [first_day, last_day] into request windows of at most `step_days` days."""
    curr = first_day
    while curr <= last_day:
        chunk_end = min(curr + timedelta(days=step_days - 1), last_day)
        yield curr, chunk_end
        curr = chunk_end + timedelta(days=1)
