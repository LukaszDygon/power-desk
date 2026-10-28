"""Date windows for incremental streams.

A stream resource owns one `dlt.sources.incremental` cursor and asks `incremental_window` what to
fetch: open-ended runs resume from the cursor (or the last fetched day, so periods without
publications are not re-fetched forever) and add at most `max_days` new days; bounded
backfills (`end_value` set) fetch their range and leave cursor and recorded window untouched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypedDict

import dlt


@dataclass(frozen=True)
class DateRange:
    """Days `first`..`last`, inclusive."""

    first: date
    last: date

    def overlaps(self, other: DateRange) -> bool:
        return self.first <= other.last and other.first <= self.last

    def chunks(self, days: int) -> Iterator[DateRange]:
        """This range split into consecutive ranges of at most `days` days."""
        first = self.first
        while first <= self.last:
            last = min(first + timedelta(days=days - 1), self.last)
            yield DateRange(first, last)
            first = last + timedelta(days=1)


@dataclass(frozen=True)
class WindowPlan:
    """The days a run fetches; `capped` when they stop short of today, so later runs must catch up."""

    days: DateRange
    capped: bool


class LastWindow(TypedDict, total=False):
    """A resource's latest open-ended window, kept in its dlt resource state as `last_window`."""

    first_day: str
    last_day: str
    capped: bool
    # file partitions only
    files_loaded: int
    cursor_last_value: str | None


def to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def day_after(day: date) -> str:
    """Exclusive `end_value` for an inclusive end date."""
    return (day + timedelta(days=1)).isoformat()


def plan_window(
    start_value: Any,
    end_value: Any | None,
    max_days: int,
    fetched_until: str | None = None,
    today: date | None = None,
) -> WindowPlan:
    """The days to fetch from a cursor's start (and exclusive end) value."""
    first_day = to_date(start_value)
    if end_value is not None:
        return WindowPlan(DateRange(first_day, to_date(end_value) - timedelta(days=1)), capped=False)
    if fetched_until:
        first_day = max(first_day, date.fromisoformat(fetched_until))
    today = today or datetime.now(UTC).date()
    cap_day = first_day + timedelta(days=max_days)
    return WindowPlan(DateRange(first_day, min(today, cap_day)), capped=cap_day < today)


def incremental_window(cursor: dlt.sources.incremental, max_days: int) -> DateRange:
    """This run's days; open-ended runs record them in resource state (`last_window`)."""
    if cursor.end_value is not None:
        return plan_window(cursor.start_value, cursor.end_value, max_days).days
    state = dlt.current.resource_state()
    previous: LastWindow = state.get("last_window", {})
    plan = plan_window(cursor.start_value, None, max_days, fetched_until=previous.get("last_day"))
    state["last_window"] = LastWindow(
        first_day=plan.days.first.isoformat(), last_day=plan.days.last.isoformat(), capped=plan.capped
    )
    return plan.days
