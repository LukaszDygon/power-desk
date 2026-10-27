"""Widget registry: dashboard cards, each a SQL query with `{start_date}` / `{end_date}` placeholders.

The registry is `data/widgets.json`; without it, the dashboard starts from `default_widgets.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from power_desk.settings import DATA_DIR

REGISTRY = DATA_DIR / "widgets.json"
DEFAULTS = Path(__file__).with_name("default_widgets.json")
WidgetType = Literal["stacked_area", "line", "bar", "donut", "kpi_cards", "table"]


class GridPosition(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 4
    minW: int = 3
    minH: int = 2


class Widget(BaseModel):
    id: str
    title: str
    type: WidgetType = "line"
    sql: str
    grid: GridPosition = Field(default_factory=GridPosition)
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


def load_widgets(path: Path = REGISTRY) -> list[dict[str, Any]]:
    return json.loads((path if path.exists() else DEFAULTS).read_text(encoding="utf-8"))


def save_widgets(widgets: list[dict[str, Any]], path: Path = REGISTRY) -> list[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(widgets, indent=2), encoding="utf-8")
    return widgets


def upsert_widget(widget: Widget, path: Path = REGISTRY) -> list[dict[str, Any]]:
    others = [w for w in load_widgets(path) if w.get("id") != widget.id]
    return save_widgets([*others, widget.model_dump()], path)


def remove_widget(widget_id: str, path: Path = REGISTRY) -> list[dict[str, Any]]:
    return save_widgets([w for w in load_widgets(path) if w.get("id") != widget_id], path)
