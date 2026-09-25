"""Tests for Elexon BMRS dlt source builder and incremental configuration."""

from __future__ import annotations

import dlt
import duckdb
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
        lag=0,
    )
    builder.add_resource(cfg)
    assert "custom_feed" in builder.configs
    assert builder.configs["custom_feed"].endpoint == "/datasets/CUSTOM"
    assert builder.configs["custom_feed"].lag == 0


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
    assert fuelinst_cfg.lag == 0

    indo_cfg = builder.configs["raw_indo"]
    assert indo_cfg.primary_key == ["settlementDate", "settlementPeriod"]
    assert indo_cfg.lag == 0


def test_incremental_pointer_advances_and_stores():
    """Verify that dlt incremental pointer advances to latest value with lag=0 across runs."""
    conn = duckdb.connect(":memory:")

    run_count = 0

    @dlt.resource(name="test_pointer_resource", write_disposition="merge", primary_key=["id"])
    def test_resource(cursor=dlt.sources.incremental("publishTime", initial_value="2021-01-01T00:00:00Z", lag=0)):
        nonlocal run_count
        run_count += 1
        if run_count == 1:
            assert cursor.last_value == "2021-01-01T00:00:00Z"
            yield [
                {"id": 1, "publishTime": "2021-01-01T12:00:00Z", "val": 100},
                {"id": 2, "publishTime": "2021-01-02T12:00:00Z", "val": 200},
            ]
        else:
            # Second run resumes strictly from the saved pointer with lag=0
            assert cursor.start_value == "2021-01-02T12:00:00Z"
            assert cursor.last_value == "2021-01-02T12:00:00Z"
            yield [
                {"id": 3, "publishTime": "2021-01-03T12:00:00Z", "val": 300},
            ]

    @dlt.source(name="test_inc_source")
    def _source():
        return [test_resource]

    pipeline = dlt.pipeline(pipeline_name="test_inc_pipeline", destination=dlt.destinations.duckdb(conn))
    pipeline.run(_source())
    state_after_run1 = pipeline.state["sources"]["test_inc_source"]["resources"]["test_pointer_resource"]["incremental"]["publishTime"]
    assert state_after_run1["last_value"] == "2021-01-02T12:00:00Z"

    # Second run
    pipeline.run(_source())
    state_after_run2 = pipeline.state["sources"]["test_inc_source"]["resources"]["test_pointer_resource"]["incremental"]["publishTime"]
    assert state_after_run2["last_value"] == "2021-01-03T12:00:00Z"
