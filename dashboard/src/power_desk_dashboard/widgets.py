"""Widget registry: dashboard cards, each a SQL query that may use the shared filter parameters (see `queries`);
a `panels` card stacks several queries' time series on one time axis, each panel toggled by the analyst.

The registry is `widgets.json` beside this module; `register-widget` adds to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

REGISTRY = Path(__file__).with_name("widgets.json")
WidgetType = Literal["area_map", "panels", "stacked_area", "line", "bar", "donut", "kpi_cards", "table"]


class GridPosition(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 4
    minW: int = 3
    minH: int = 2


class Panel(BaseModel):
    """A time series of a `panels` card, on the card's shared time axis."""

    id: str
    title: str
    type: Literal["line", "stacked_area"] = "line"
    sql: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class Widget(BaseModel):
    id: str
    title: str
    type: WidgetType = "line"
    sql: str = ""  # empty for a `panels` card, whose panels hold the queries
    panels: list[Panel] = Field(default_factory=list)
    grid: GridPosition = Field(default_factory=GridPosition)
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    @property
    def queries(self) -> list[str]:
        """Every query the card runs."""
        return [sql for sql in [self.sql, *(panel.sql for panel in self.panels)] if sql]


def load_widgets(path: Path = REGISTRY) -> list[Widget]:
    """The registry's widgets; an entry that does not match `Widget` fails with the offending field."""
    return [Widget.model_validate(entry) for entry in json.loads(path.read_text(encoding="utf-8"))]


def upsert_widget(widget: Widget, path: Path = REGISTRY) -> None:
    widgets = [*(w for w in load_widgets(path) if w.id != widget.id), widget]
    path.write_text(json.dumps([w.model_dump() for w in widgets], indent=2) + "\n", encoding="utf-8")
