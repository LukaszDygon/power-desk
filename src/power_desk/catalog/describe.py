"""Describe the queryable relations from the dbt manifest.

    uv run python -m power_desk.catalog.describe                 # list relations by layer
    uv run python -m power_desk.catalog.describe mart_gb_generation_mix   # columns of one relation

Reads `transform/target/manifest.json` (refresh with `dbt parse` or `dbt build`).
"""

from __future__ import annotations

import argparse
import json
import sys

from power_desk.catalog.text import plain_summary
from power_desk.settings import dbt_manifest_path

LAYERS = ("marts", "ods", "staging", "raw")


def relations(manifest: dict) -> dict[str, dict]:
    nodes = [n for n in manifest["nodes"].values() if n["resource_type"] in ("model", "seed")]
    nodes += list(manifest["sources"].values())
    return {(n.get("identifier") or n.get("alias") or n["name"]): n for n in nodes}


def print_relation(name: str, node: dict) -> None:
    """A relation's description and its columns."""
    print(f"{node['schema']}.{name}: {plain_summary(node.get('description', ''))}\n")
    for column, col in node.get("columns", {}).items():
        print(f"  {column:<28} {plain_summary(col.get('description', ''), paragraphs=1)}")


def print_layers(rels: dict[str, dict]) -> None:
    """Every relation with a one-line summary, by layer."""
    for layer in LAYERS:
        names = sorted(n for n, node in rels.items() if node["schema"] == layer)
        if names:
            print(f"[{layer}]")
            for name in names:
                print(f"  {name:<28} {plain_summary(rels[name].get('description', ''), paragraphs=1)[:110]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    parser.add_argument("relation", nargs="?", help="relation name, e.g. mart_gb_generation_mix")
    args = parser.parse_args()

    path = dbt_manifest_path()
    if not path.exists():
        print(
            f"no dbt manifest at {path}; run `uv run dbt parse --project-dir transform --profiles-dir transform`",
            file=sys.stderr,
        )
        return 1
    rels = relations(json.loads(path.read_text(encoding="utf-8")))
    if not args.relation:
        print_layers(rels)
        return 0
    if args.relation not in rels:
        print(f"unknown relation {args.relation!r}", file=sys.stderr)
        return 1
    print_relation(args.relation, rels[args.relation])
    return 0


if __name__ == "__main__":
    sys.exit(main())
