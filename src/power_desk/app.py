"""FastAPI Web Server for Power Desk Analyst Dashboard.

Exposes REST endpoints for DuckDB queries, lineage graphs, filter options,
widget registry, and renders the high-density minimalist analyst UI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import uvicorn

from power_desk.db import get_db
from power_desk.widgets import add_or_update_widget, load_widgets, remove_widget

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Power Desk",
    description="Minimalist Analyst Dashboard for UK Power & Energy Data",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR.as_posix()), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR.as_posix())


class QueryPayload(BaseModel):
    sql: str
    params: list[Any] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None


class WidgetPayload(BaseModel):
    id: str
    title: str
    type: str
    sql: str
    grid: dict[str, int] = Field(default_factory=dict)
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request):
    """Renders the primary analyst dashboard."""
    db = get_db()
    filters = db.get_filter_options()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "filters": filters,
            "title": "Power Desk // UK Grid Terminal",
        },
    )


@app.get("/api/filters")
async def api_get_filters():
    """Returns available date boundaries, settlement periods, and fuel types."""
    db = get_db()
    return db.get_filter_options()


@app.get("/api/lineage")
async def api_get_lineage():
    """Returns DAG nodes and edges for Cytoscape.js lineage visualization."""
    db = get_db()
    return db.get_lineage()


@app.get("/api/widgets")
async def api_get_widgets():
    """Returns list of registered dashboard widgets."""
    return load_widgets()


@app.post("/api/widgets")
async def api_save_widget(payload: WidgetPayload):
    """Adds or updates a widget in the active dashboard registry."""
    updated = add_or_update_widget(payload.model_dump())
    return {"status": "ok", "widgets": updated}


@app.delete("/api/widgets/{widget_id}")
async def api_delete_widget(widget_id: str):
    """Deletes a widget from the active dashboard registry."""
    updated = remove_widget(widget_id)
    return {"status": "ok", "widgets": updated}


@app.post("/api/query")
async def api_run_query(payload: QueryPayload):
    """Safely executes a read-only DuckDB SQL query with date placeholders replaced."""
    db = get_db()
    sql = payload.sql

    # Replace parameter placeholders if provided
    if payload.start_date:
        sql = sql.replace("{start_date}", payload.start_date)
    if payload.end_date:
        sql = sql.replace("{end_date}", payload.end_date)

    try:
        result = db.execute_query(sql, payload.params)
        return result
    except Exception as exc:
        logger.error("Query failed: %s | Error: %s", sql, exc)
        raise HTTPException(status_code=400, detail=str(exc))


def main() -> None:
    """CLI Entrypoint for running the Power Desk server."""
    uvicorn.run("power_desk.app:app", host="127.0.0.1", port=8888, reload=True)


if __name__ == "__main__":
    main()
