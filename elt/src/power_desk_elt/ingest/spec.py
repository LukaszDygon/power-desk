"""What the registry, orchestrator and CLIs need to know about a source, the days a run covers, and the
default write disposition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta

from dlt.common.schema.typing import TMergeDispositionDict
from dlt.sources import DltSource

from power_desk_elt.ingest.windows import to_date
from power_desk_elt.settings import backfill_start_date

# every version of a row kept (ADR 0003); a resource adds its `merge_key` where only its keys may close
SCD2: TMergeDispositionDict = {"disposition": "merge", "strategy": "scd2"}


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


@dataclass(frozen=True)
class SourceSpec:
    """A dlt source and its run limits; `name` is the dlt source, schema and pipeline name.

    `window_padding_days` widens requested date ranges for publishers whose local dates
    cross UTC day boundaries. `references` names the warehouse relations (`<schema>.<model>`, dbt
    models) the source's resources read, e.g. the sites to read weather for: they are built before the
    source loads (the orchestrator's asset dependencies, the seed load, an acceptance run). `requires`
    names the sources those relations are built from, loaded first by an acceptance run.
    """

    name: str
    build: Callable[[RunWindow], DltSource]  # the source module's `@dlt.source` function
    max_days_per_run: int = 7
    window_padding_days: int = 0
    references: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()

    def window(
        self, start: date | str | None = None, end: date | str | None = None, max_days: int | None = None
    ) -> RunWindow:
        """A run window from caller input; defaults: `POWER_DESK_START_DATE`, open-ended, `max_days_per_run`."""
        return RunWindow(
            start=to_date(start or backfill_start_date()),
            end=to_date(end) if end else None,
            max_days=self.max_days_per_run if max_days is None else max_days,
        )
