"""What the registry, orchestrator and CLIs need to know about a source, and the days a run covers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Protocol

from dlt.sources import DltSource

from power_desk.ingest.windows import to_date
from power_desk.settings import backfill_start_date


@dataclass(frozen=True)
class RunWindow:
    """The days a source run covers.

    Open-ended (`end` None): resume from the cursor (from `start` when there is none) and add at
    most `max_days` new days. Bounded backfill: `start`..`end` inclusive, leaving cursors and
    recorded windows untouched.
    """

    start: date
    end: date | None
    max_days: int

    @property
    def bounded(self) -> bool:
        return self.end is not None

    def padded(self, days: int) -> RunWindow:
        """Widened by `days` on both sides."""
        padding = timedelta(days=days)
        return replace(self, start=self.start - padding, end=self.end + padding if self.end else None)


class SourceBuilder(Protocol):
    """The `@dlt.source` function of a source module."""

    def __call__(self, window: RunWindow) -> DltSource: ...


@dataclass(frozen=True)
class SourceSpec:
    """A dlt source and its run limits; `name` is the dlt source, schema and pipeline name.

    `window_padding_days` widens requested date ranges for publishers whose local dates
    cross UTC day boundaries.
    """

    name: str
    build: SourceBuilder
    max_days_per_run: int = 7
    window_padding_days: int = 0

    def window(
        self, start: date | str | None = None, end: date | str | None = None, max_days: int | None = None
    ) -> RunWindow:
        """A run window from caller input; defaults: `POWER_DESK_START_DATE`, open-ended, `max_days_per_run`."""
        return RunWindow(
            start=to_date(start or backfill_start_date()),
            end=to_date(end) if end else None,
            max_days=self.max_days_per_run if max_days is None else max_days,
        )
