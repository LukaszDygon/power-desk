"""The catalogue: generated dbt sources and docs are current, and every warehouse column is documented."""

from __future__ import annotations

import json
from pathlib import Path

from power_desk.catalog.generate import generate
from power_desk.settings import dbt_manifest_path
from tests.support import query


def test_generated_catalogue_is_up_to_date():
    stale = [
        str(path) for path, text in generate().items() if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    assert not stale, f"run `uv run python -m power_desk.catalog.generate`: {stale}"


def test_every_warehouse_column_is_documented(seeded_warehouse: Path):
    manifest = json.loads(dbt_manifest_path().read_text(encoding="utf-8"))
    nodes = [
        n
        for n in [*manifest["nodes"].values(), *manifest["sources"].values()]
        if n["resource_type"] in ("model", "seed", "source")
    ]
    assert not [n["unique_id"] for n in nodes if not n["description"].strip()]
    documented = {
        (n["schema"], n.get("identifier") or n.get("alias") or n["name"]): {
            c for c, col in n["columns"].items() if col["description"].strip() and "{{" not in col["description"]
        }
        for n in nodes
    }
    columns = query(
        seeded_warehouse,
        """
        select table_schema, table_name, column_name from information_schema.columns
        where table_schema in ('raw', 'staging', 'ods', 'dims', 'marts', 'dlt_meta') and table_name <> '_dlt_version'
    """,
    )
    assert not sorted(f"{s}.{t}.{c}" for s, t, c in columns if c not in documented.get((s, t), set()))
