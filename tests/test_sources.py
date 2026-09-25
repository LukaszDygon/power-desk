"""Tests for Elexon BMRS dlt source builder and incremental configuration."""

from __future__ import annotations

import pytest
from power_desk.sources.bmrs import (
    BmrsResourceConfig,
    BmrsSourceBuilder,
    build_default_bmrs_source,
    get_default_builder,
)


def test_builder_resource_registration():
    builder = BmrsSourceBuilder()
    cfg = BmrsResourceConfig(
        name="custom_feed",
        endpoint="/datasets/CUSTOM",
        primary_key=["settlementDate", "settlementPeriod", "id"],
        cursor_field="settlementDate",
    )
    builder.add_resource(cfg)
    assert "custom_feed" in builder.configs
    assert builder.configs["custom_feed"].endpoint == "/datasets/CUSTOM"


def test_default_source_has_merge_disposition():
    source = build_default_bmrs_source(initial_date="2024-01-01", end_date="2024-01-01")
    expected_resources = [
        "raw_fuelinst",
        "raw_indo",
        "raw_itsdo",
        "raw_demand_forecast",
        "raw_windfor",
    ]

    for res_name in expected_resources:
        assert res_name in source.resources
        resource = source.resources[res_name]
        schema = resource.compute_table_schema()
        assert schema.get("write_disposition") == "merge"


def test_natural_keys_configured():
    builder = get_default_builder()
    fuelinst_cfg = builder.configs["raw_fuelinst"]
    assert "settlementDate" in fuelinst_cfg.primary_key
    assert "settlementPeriod" in fuelinst_cfg.primary_key
    assert "fuelType" in fuelinst_cfg.primary_key

    indo_cfg = builder.configs["raw_indo"]
    assert indo_cfg.primary_key == ["settlementDate", "settlementPeriod"]
