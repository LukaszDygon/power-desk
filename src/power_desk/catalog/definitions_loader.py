"""Load and merge `catalog/definitions/*.yml` and the provider snapshots.

Each definitions file may contain the sections `sources`, `tables`, `columns`,
`dlt_tables`, `freshness` and `links` (named official documents, cited by tables and columns
via `links: [name]`); keys must be unique across files. One file per source
(its dbt source, raw tables and source-specific column concepts) plus shared files for
cross-source concepts keeps every definition in exactly one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent
DEFINITIONS_DIR = CATALOG_DIR / "definitions"
SNAPSHOTS_DIR = CATALOG_DIR / "snapshots"
SECTIONS = ("sources", "tables", "columns", "dlt_tables", "freshness", "links")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_definitions(directory: Path = DEFINITIONS_DIR) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {section: {} for section in SECTIONS}
    origin: dict[tuple[str, str], str] = {}
    for path in sorted(directory.glob("*.yml")):
        doc = load_yaml(path)
        unknown = set(doc) - set(SECTIONS)
        if unknown:
            raise KeyError(f"{path.name}: unknown sections {sorted(unknown)}; allowed {SECTIONS}")
        for section, entries in doc.items():
            for key, value in (entries or {}).items():
                if (section, key) in origin:
                    raise KeyError(f"{section}.{key} defined in both {origin[section, key]} and {path.name}")
                origin[section, key] = path.name
                merged[section][key] = value
    for table, entry in merged["tables"].items():
        preset = entry.get("freshness")
        if isinstance(preset, str):
            if preset not in merged["freshness"]:
                raise KeyError(f"tables.{table}: unknown freshness preset {preset!r}")
            entry["freshness"] = merged["freshness"][preset]
    for section in ("tables", "columns"):
        for key, entry in merged[section].items():
            unknown_links = set(entry.get("links", [])) - set(merged["links"])
            if unknown_links:
                raise KeyError(f"{section}.{key}: unknown links {sorted(unknown_links)}")
    return merged


def referenced(definitions: dict[str, Any]) -> list[str]:
    """Every provider reference used by tables and columns."""
    refs = set()
    for section in ("tables", "columns"):
        for entry in definitions[section].values():
            refs.update(entry.get("refs", []))
    return sorted(refs)


def load_snapshots(directory: Path = SNAPSHOTS_DIR) -> dict[str, dict[str, Any]]:
    """{provider: {retrieved, entries: {"kind/id": entry}}}."""
    return {path.stem: load_yaml(path) for path in sorted(directory.glob("*.yml"))}
