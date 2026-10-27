"""What the registry, orchestrator and CLIs need to know about a source."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dlt.sources import DltSource


@dataclass(frozen=True)
class SourceSpec:
    """A dlt source and its run limits; `name` is the dlt source, schema and pipeline name.

    `build` is the `@dlt.source` function, called as `build(initial_date, end_date, max_days_per_run)`.
    `window_padding_days` widens requested date ranges for publishers whose local dates
    cross UTC day boundaries.
    """

    name: str
    build: Callable[..., DltSource]
    max_days_per_run: int = 7
    window_padding_days: int = 0
