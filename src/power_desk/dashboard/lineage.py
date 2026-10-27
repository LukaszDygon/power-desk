"""Lineage graph for the dashboard: publisher -> raw table -> dbt models -> widget."""

from __future__ import annotations

import json
import re
from typing import Any

from power_desk.catalog.text import plain_summary
from power_desk.dashboard.widgets import load_widgets
from power_desk.settings import dbt_manifest_path

MODEL_NODE_TYPES = {"staging": "staging_view", "ods": "ods_view", "marts": "mart_view"}
Graph = dict[str, list[dict[str, Any]]]


def lineage() -> Graph:
    path = dbt_manifest_path()
    if not path.exists():
        return {"nodes": [], "edges": []}
    return lineage_from_manifest(json.loads(path.read_text(encoding="utf-8")), load_widgets())


def lineage_from_manifest(manifest: dict[str, Any], widgets: list[dict[str, Any]]) -> Graph:
    graph: Graph = {"nodes": [], "edges": []}
    ids = add_sources(graph, manifest) | add_models(graph, manifest)
    add_model_edges(graph, manifest, ids)
    add_widgets(graph, widgets, {node["id"] for node in graph["nodes"] if node["type"] in MODEL_NODE_TYPES.values()})
    return graph


def add_sources(graph: Graph, manifest: dict[str, Any]) -> dict[str, str]:
    """Publisher and raw table nodes per dlt-loaded source table; returns {unique_id: node id}."""
    ids = {}
    for unique_id, source in manifest.get("sources", {}).items():
        if source["source_name"] == "dlt":
            continue
        table, dlt_meta = source["name"], source.get("config", {}).get("meta", {}).get("dlt", {})
        graph["nodes"] += [
            {
                "id": f"api_{table}",
                "label": f"{source['source_name'].upper()} ({dlt_meta.get('resource', table)})",
                "type": "source",
                "desc": plain_summary(source.get("source_description")),
            },
            {"id": table, "label": table, "type": "raw_table", "desc": plain_summary(source.get("description"))},
        ]
        graph["edges"].append(
            {"source": f"api_{table}", "target": table, "label": f"dlt {dlt_meta.get('write_disposition', 'load')}"}
        )
        ids[unique_id] = table
    return ids


def add_models(graph: Graph, manifest: dict[str, Any]) -> dict[str, str]:
    ids = {}
    for unique_id, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") == "model" and node.get("schema") in MODEL_NODE_TYPES:
            graph["nodes"].append(
                {
                    "id": node["name"],
                    "label": node["name"],
                    "type": MODEL_NODE_TYPES[node["schema"]],
                    "desc": plain_summary(node.get("description")),
                }
            )
            ids[unique_id] = node["name"]
    return ids


def add_model_edges(graph: Graph, manifest: dict[str, Any], ids: dict[str, str]) -> None:
    for unique_id, node in manifest.get("nodes", {}).items():
        if unique_id not in ids or node.get("resource_type") != "model":
            continue
        label = f"dbt {node.get('config', {}).get('materialized', '')}"
        graph["edges"] += [
            {"source": ids[dep], "target": ids[unique_id], "label": label}
            for dep in node.get("depends_on", {}).get("nodes", [])
            if dep in ids
        ]


def add_widgets(graph: Graph, widgets: list[dict[str, Any]], models: set[str]) -> None:
    for widget in widgets:
        queried = {
            name
            for name in re.findall(r"\b(?:from|join)\s+(?:\w+\.)?(\w+)", widget.get("sql", ""), re.I)
            if name in models
        }
        if queried:
            widget_id = f"widget_{widget['id']}"
            graph["nodes"].append(
                {
                    "id": widget_id,
                    "label": f"Widget: {widget['title']}",
                    "type": "widget",
                    "desc": widget.get("description", ""),
                }
            )
            graph["edges"] += [{"source": model, "target": widget_id, "label": "query"} for model in sorted(queried)]
