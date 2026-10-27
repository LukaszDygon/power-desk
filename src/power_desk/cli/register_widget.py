"""Validate a widget's SQL over the warehouse's loaded dates and add it to the dashboard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import get_args

from pydantic import ValidationError

from power_desk.dashboard import queries
from power_desk.dashboard.widgets import GridPosition, Widget, WidgetType, upsert_widget


def parse_widget() -> Widget:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-file", type=Path, help="widget specification (JSON)")
    parser.add_argument("--id")
    parser.add_argument("--title")
    parser.add_argument("--type", choices=get_args(WidgetType), default="line")
    parser.add_argument("--sql", help="DuckDB query with {start_date} / {end_date} placeholders")
    parser.add_argument("--w", type=int, default=6, help="grid width (1-12 columns)")
    parser.add_argument("--h", type=int, default=4, help="grid height")
    parser.add_argument("--config", default="{}", help="visual configuration (JSON)")
    args = parser.parse_args()
    try:
        if args.json_file:
            return Widget.model_validate_json(args.json_file.read_text(encoding="utf-8"))
        return Widget(
            id=args.id,
            title=args.title,
            type=args.type,
            sql=args.sql,
            grid=GridPosition(w=args.w, h=args.h),
            config=json.loads(args.config),
        )
    except ValidationError as exc:
        parser.error(str(exc))


def main() -> int:
    widget = parse_widget()
    options = queries.filter_options()
    try:
        result = queries.run_query(
            queries.bind_dates(widget.sql, start_date=options["min_date"], end_date=options["max_date"])
        )
    except Exception as exc:
        print(f"✗ {widget.id}: query failed: {exc}", file=sys.stderr)
        return 1
    print(f"✓ {widget.id}: {result['row_count']} rows, columns {result['columns']} ({result['duration_ms']} ms)")
    upsert_widget(widget)
    print(f"✓ registered {widget.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
