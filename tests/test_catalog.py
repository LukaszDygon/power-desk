"""Catalogue: generated files are current, every column is documented, Elexon parsing."""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pytest

from power_desk.catalog import generate as gen
from power_desk.catalog.definitions_loader import load_definitions, load_snapshots, referenced
from power_desk.catalog.providers import PROVIDERS, parse_ref
from power_desk.catalog.providers.elexon import dataset_definitions, parse_glossary_page


def test_generated_catalogue_is_up_to_date():
    stale = [path.name for path, text in gen.generate().items() if not path.exists() or path.read_text() != text]
    assert not stale, f"run `uv run python -m power_desk.catalog.generate`: {stale}"


def test_sources_reference_doc_blocks_and_map_to_dagster_assets():
    text = next(t for p, t in gen.generate().items() if p.name == "bmrs.yml")
    assert "asset_key:\n          - raw\n          - raw_fuelinst" in text
    assert "name: raw_fuelinst_unique_natural_key" in text
    assert "description: '{{ doc(''dataset_fuelinst'') }}'" in text
    assert "description: '{{ doc(''col_indo_demand'') }}'" in text  # dataset-specific mapping of `demand`


def test_undocumented_raw_column_fails_generation():
    catalogue = gen.Catalogue(load_definitions(), load_snapshots())
    with pytest.raises(KeyError, match="raw_indo.brand_new_field"):
        catalogue.column_key("raw_indo", "brand_new_field")


def test_every_reference_resolves_to_a_snapshot_entry():
    snapshots = load_snapshots()
    for ref in referenced(load_definitions()):
        provider, kind, ident = parse_ref(ref)
        assert provider in PROVIDERS
        assert f"{kind}/{ident}" in snapshots[provider]["entries"], ref


def test_definition_keys_must_be_unique_across_files(tmp_path):
    (tmp_path / "a.yml").write_text("columns:\n  dup: {description: one}\n")
    (tmp_path / "b.yml").write_text("columns:\n  dup: {description: two}\n")
    with pytest.raises(KeyError, match="columns.dup defined in both a.yml and b.yml"):
        load_definitions(tmp_path)


def test_every_warehouse_column_is_documented(seeded_warehouse: Path):
    manifest = json.loads(Path(os.environ["POWER_DESK_DBT_MANIFEST"]).read_text())
    documented = {}
    for node in [*manifest["nodes"].values(), *manifest["sources"].values()]:
        if node["resource_type"] in ("model", "seed", "source"):
            assert node["description"].strip(), f"{node['unique_id']} has no description"
            identifier = node.get("identifier") or node.get("alias") or node["name"]
            documented[(node["schema"], identifier)] = {
                c for c, col in node["columns"].items() if col["description"].strip() and "{{" not in col["description"]
            }
    con = duckdb.connect(str(seeded_warehouse), read_only=True)
    actual = con.execute("""
        select table_schema, table_name, column_name from information_schema.columns
        where table_schema in ('raw', 'staging', 'ods', 'dims', 'marts', 'dlt_meta') and table_name <> '_dlt_version'
    """).fetchall()
    con.close()
    undocumented = sorted(f"{s}.{t}.{c}" for s, t, c in actual if c not in documented.get((s, t), set()))
    assert not undocumented, f"columns without a description: {undocumented}"


GLOSSARY_PAGE = """
<html><body><nav>Menu</nav><main>
<h1>Glossary Term: Settlement Period</h1>
<p>Acronym: j</p>
<p>Settlement Periods always refer to local time (whether this is GMT or BST).</p>
<p><a href="https://www.elexon.co.uk/bsc/settlement/">Settlement Period conversion table&nbsp;</a></p>
<h3>BSC defined definition</h3>
<p>A period of 30 minutes beginning on the hour or the half-hour.</p>
<h3>BSC documentation</h3>
<p><a href="https://www.elexon.co.uk/x-2/">BSC Section X, Annex X-2</a></p>
<h3>Related terms</h3>
<p><a href="/spot-time/">Spot Time</a></p>
<p>Suggest content changes</p>
</main><script>var noise = "Glossary Term: Settlement Period";</script></body></html>
"""


def test_parse_glossary_page_splits_sections_and_keeps_links():
    parsed = parse_glossary_page(GLOSSARY_PAGE, "Settlement Period")
    assert parsed == {
        "acronym": "j",
        "summary": "Settlement Periods always refer to local time (whether this is GMT or BST).\n"
                   "[Settlement Period conversion table](https://www.elexon.co.uk/bsc/settlement/)",
        "definition": "A period of 30 minutes beginning on the hour or the half-hour.",
        "reference": "[BSC Section X, Annex X-2](https://www.elexon.co.uk/x-2/)",
    }


def test_dataset_definitions_drop_api_usage_notes():
    spec = {"paths": {"/datasets/INDO": {"get": {
        "summary": "Initial National Demand outturn (INDO)",
        "description": "Initial demand in MW.\n            \nSpecific publish time filters may be supplied, otherwise latest.",
    }}}}
    assert dataset_definitions(spec, ["INDO"])["INDO"]["summary"] == "Initial demand in MW."
