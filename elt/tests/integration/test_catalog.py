"""The catalogue: generated dbt sources, docs and data contracts are current; every warehouse column is documented."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from power_desk_elt.catalog.contracts import CONTRACTS_DIR, ODCS_VERSION, export
from power_desk_elt.catalog.generate import generate
from power_desk_elt.settings import dbt_manifest_path
from tests.support import query


def test_generated_catalogue_is_up_to_date():
    stale = [
        str(path) for path, text in generate().items() if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    assert not stale, f"run `uv run python -m power_desk_elt.catalog.generate`: {stale}"


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


def test_data_contracts_are_up_to_date_and_valid_odcs(seeded_warehouse: Path):
    outputs = export(json.loads(dbt_manifest_path().read_text(encoding="utf-8")), seeded_warehouse)
    stale = [str(p) for p, text in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    orphans = [str(p) for p in set(CONTRACTS_DIR.glob("*/*.odcs.yaml")) - set(outputs)]
    assert not stale + orphans, f"run `uv run python -m power_desk_elt.catalog.contracts`: {stale + orphans}"
    schema = json.loads((CONTRACTS_DIR / f"odcs-json-schema-{ODCS_VERSION}.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft201909Validator(schema)
    errors = {p.name: e.message for p, text in outputs.items() for e in validator.iter_errors(yaml.safe_load(text))}
    assert not errors
