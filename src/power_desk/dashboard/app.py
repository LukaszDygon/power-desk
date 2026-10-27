"""Dashboard web app: the page, and JSON endpoints for queries, filters, lineage and widgets."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from power_desk import warehouse
from power_desk.dashboard import queries
from power_desk.dashboard.lineage import lineage
from power_desk.dashboard.widgets import Widget, load_widgets, remove_widget, upsert_widget

HERE = Path(__file__).resolve().parent

app = FastAPI(title="Power Desk", description="Analyst dashboard for power and energy data")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


class Query(BaseModel):
    sql: str
    start_date: date | None = None
    end_date: date | None = None


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={"filters": queries.filter_options(), "title": "Power Desk"}
    )


@app.get("/api/filters")
def filters() -> dict[str, Any]:
    return queries.filter_options()


@app.get("/api/lineage")
def lineage_graph() -> dict[str, Any]:
    return lineage()


@app.get("/api/widgets")
def widgets() -> list[Widget]:
    return load_widgets()


@app.post("/api/widgets")
def save_widget(widget: Widget) -> dict[str, Any]:
    return {"status": "ok", "widgets": upsert_widget(widget)}


@app.delete("/api/widgets/{widget_id}")
def delete_widget(widget_id: str) -> dict[str, Any]:
    return {"status": "ok", "widgets": remove_widget(widget_id)}


@app.post("/api/query")
def query(payload: Query) -> dict[str, Any]:
    """400 for a query the warehouse rejects, 503 while the warehouse stays locked by a load."""
    try:
        return queries.run_query(payload.sql, payload.start_date, payload.end_date)
    except duckdb.Error as exc:
        status = 503 if warehouse.is_lock_error(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


def main() -> None:
    uvicorn.run("power_desk.dashboard.app:app", host="127.0.0.1", port=8888, reload=True)
