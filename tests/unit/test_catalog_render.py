import pytest

from power_desk.catalog import CatalogError
from power_desk.catalog.definitions_loader import load_definitions
from power_desk.catalog.providers.elexon import dataset_definitions, parse_glossary_page
from power_desk.catalog.render import Catalogue

SNAPSHOTS = {
    "elexon": {
        "retrieved": "2026-10-26",
        "entries": {
            "datasets/INDO": {
                "title": "Initial National Demand outturn (INDO)",
                "summary": "Initial demand in MW.",
                "url": "https://x/INDO",
            },
        },
    }
}
DEFINITIONS = {
    "links": {"ddd": {"title": "Detailed Data Descriptions", "url": "https://x/ddd.pdf"}},
    "tables": {"bmrs__indo": {"refs": ["elexon:datasets/INDO"], "columns": {"demand": "indo_demand"}}},
    "columns": {
        "indo_demand": {"description": "Demand in MW.", "links": [{"link": "ddd", "section": "Total load", "page": 19}]}
    },
}


def test_dataset_without_description_uses_the_publishers_wording_and_cites_it_as_metadata():
    catalogue = Catalogue(DEFINITIONS, SNAPSHOTS)
    assert catalogue.dataset_md("bmrs__indo") == "**Initial National Demand outturn (INDO)**\n\nInitial demand in MW."
    assert catalogue.references(catalogue.tables["bmrs__indo"]) == [
        {
            "title": "Elexon Insights API: Initial National Demand outturn (INDO)",
            "url": "https://x/INDO",
            "id": "elexon:datasets/INDO",
            "retrieved": "2026-10-26",
        }
    ]


def test_column_text_keeps_citations_out_of_the_description():
    catalogue = Catalogue(DEFINITIONS, SNAPSHOTS)
    assert catalogue.column_md("indo_demand") == "Demand in MW."
    assert catalogue.references(catalogue.columns["indo_demand"]) == [
        {"title": "Detailed Data Descriptions", "url": "https://x/ddd.pdf", "section": "Total load", "page": 19}
    ]


def test_undocumented_raw_column_is_an_error():
    with pytest.raises(CatalogError, match="bmrs__indo.brand_new_field"):
        Catalogue(DEFINITIONS, SNAPSHOTS).column_key("bmrs__indo", "brand_new_field")


def test_definition_keys_must_be_unique_across_files(tmp_path):
    (tmp_path / "a.yml").write_text("columns:\n  dup: {description: one}\n")
    (tmp_path / "b.yml").write_text("columns:\n  dup: {description: two}\n")
    with pytest.raises(CatalogError, match="columns.dup defined in both a.yml and b.yml"):
        load_definitions(tmp_path)


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
    assert parse_glossary_page(GLOSSARY_PAGE, "Settlement Period") == {
        "acronym": "j",
        "summary": "Settlement Periods always refer to local time (whether this is GMT or BST).\n"
        "[Settlement Period conversion table](https://www.elexon.co.uk/bsc/settlement/)",
        "definition": "A period of 30 minutes beginning on the hour or the half-hour.",
        "reference": "[BSC Section X, Annex X-2](https://www.elexon.co.uk/x-2/)",
    }


def test_dataset_definitions_drop_api_usage_notes():
    spec = {
        "paths": {
            "/datasets/INDO": {
                "get": {
                    "summary": "Initial National Demand outturn (INDO)",
                    "description": "Initial demand in MW.\n            \n"
                    "Specific publish time filters may be supplied, otherwise latest.",
                }
            }
        }
    }
    assert dataset_definitions(spec, ["INDO"])["INDO"]["summary"] == "Initial demand in MW."
