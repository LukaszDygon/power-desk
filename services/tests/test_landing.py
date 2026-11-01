from __future__ import annotations

from pathlib import Path

from samples import landed_files, landed_rows

from power_desk_services.landing import Landing


def test_land_appends_rows_per_table_as_published(landing: Landing, landing_root: Path) -> None:
    landing.land({"fuelinst": [{"fuelType": "WIND", "generation": 9000}], "empty": []})
    landing.land({"fuelinst": [{"fuelType": "CCGT", "generation": 5000}]})

    rows = landed_rows(landing_root, "fuelinst")

    assert [(r["fuel_type"], r["generation"]) for r in rows] == [("WIND", 9000), ("CCGT", 5000)]
    assert len({r["_dlt_load_id"] for r in rows}) == 2
    assert not landed_files(landing_root, "empty")


def test_land_without_rows_is_no_load(landing: Landing, landing_root: Path) -> None:
    landing.land({"fuelinst": []})

    assert not landing_root.exists()
