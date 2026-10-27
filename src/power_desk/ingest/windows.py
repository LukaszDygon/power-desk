"""Date windows for incremental streams.

A stream resource owns one `dlt.sources.incremental` cursor and asks `incremental_window` what to
fetch: open-ended runs resume from the cursor (or the last fetched day, so periods without
publications are not re-fetched forever) and add at most `max_days_per_run` new days; bounded
backfills (`end_value` set) fetch their range and leave cursor and recorded window untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import dlt


def to_date(value: Any) -> date:
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
    """(first_day, last_day, capped) to fetch; `capped` when the window stops short of today."""
    first_day = to_date(start_value)
    if end_value is not None:
        return first_day, to_date(end_value) - timedelta(days=1), False
    if fetched_until:
        first_day = max(first_day, date.fromisoformat(fetched_until))
    today = today or datetime.now(UTC).date()
    cap_day = first_day + timedelta(days=max_days_per_run)
    return first_day, min(today, cap_day), cap_day < today


def incremental_window(cursor: dlt.sources.incremental, max_days_per_run: int) -> tuple[date, date]:
    """This run's window; open-ended runs record it in resource state (`last_window`)."""
    if cursor.end_value is not None:
        first_day, last_day, _ = plan_window(cursor.start_value, cursor.end_value, max_days_per_run)
        return first_day, last_day
    state = dlt.current.resource_state()
    previous = state.get("last_window", {}).get("last_day")
    first_day, last_day, capped = plan_window(cursor.start_value, None, max_days_per_run, fetched_until=previous)
    state["last_window"] = {"first_day": first_day.isoformat(), "last_day": last_day.isoformat(), "capped": capped}
    return first_day, last_day


def day_windows(first_day: date, last_day: date, step_days: int) -> Iterator[tuple[date, date]]:
    """[first_day, last_day] split into windows of at most `step_days` days."""
    while first_day <= last_day:
        window_end = min(first_day + timedelta(days=step_days - 1), last_day)
        yield first_day, window_end
        first_day = window_end + timedelta(days=1)
