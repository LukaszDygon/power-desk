#!/usr/bin/env python3
"""CLI utility to validate and register a new analytical widget into Power Desk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from power_desk.db import get_db
from power_desk.widgets import add_or_update_widget


def validate_sql(sql: str) -> dict:
    """Verifies that the SQL executes against DuckDB with sample dates."""
    db = get_db()
    test_sql = sql.replace("{start_date}", "2024-03-01").replace("{end_date}", "2024-03-07")
    return db.execute_query(test_sql)


def register_widget(widget_data: dict) -> None:
    """Validates SQL and persists widget."""
    w_id = widget_data.get("id")
    title = widget_data.get("title")
    sql = widget_data.get("sql")
    w_type = widget_data.get("type", "line")

    if not w_id or not title or not sql:
        print("Error: 'id', 'title', and 'sql' are mandatory fields.", file=sys.stderr)
        sys.exit(1)

    print(f"Validating SQL for widget '{title}' ({w_id})...")
    try:
        res = validate_sql(sql)
        print(f"  ✓ SQL valid! Returned {res['row_count']} rows and columns: {res['columns']} in {res['duration_ms']}ms")
    except Exception as exc:
        print(f"  ✗ SQL Validation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Ensure grid defaults
    if "grid" not in widget_data:
        widget_data["grid"] = { "x": 0, "y": 0, "w": 6, "h": 4, "minW": 3, "minH": 2 }

    add_or_update_widget(widget_data)
    print(f"✓ Successfully registered widget '{w_id}' to dashboard!")


def main():
    parser = argparse.ArgumentParser(description="Register a new widget into Power Desk dashboard")
    parser.add_argument("--json-file", type=str, help="Path to JSON file containing widget specification")
    parser.add_argument("--id", type=str, help="Unique widget ID slug")
    parser.add_argument("--title", type=str, help="Widget card title")
    parser.add_argument("--type", type=str, choices=["stacked_area", "line", "bar", "donut", "kpi_cards", "table"], default="line")
    parser.add_argument("--sql", type=str, help="DuckDB SQL query template")
    parser.add_argument("--w", type=int, default=6, help="Grid width (columns 1-12)")
    parser.add_argument("--h", type=int, default=4, help="Grid height")
    parser.add_argument("--config", type=str, default="{}", help="Visual configuration as JSON string")

    args = parser.parse_args()

    if args.json_file:
        data = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        register_widget(data)
    elif args.id and args.title and args.sql:
        config = json.loads(args.config)
        data = {
            "id": args.id,
            "title": args.title,
            "type": args.type,
            "sql": args.sql,
            "grid": { "x": 0, "y": 0, "w": args.w, "h": args.h, "minW": 3, "minH": 2 },
            "config": config,
        }
        register_widget(data)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
