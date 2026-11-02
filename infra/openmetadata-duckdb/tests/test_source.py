from __future__ import annotations

import os
from pathlib import Path
import re

import duckdb
from metadata.generated.schema.api.data.createDatabase import CreateDatabaseRequest
from metadata.generated.schema.api.data.createDatabaseSchema import CreateDatabaseSchemaRequest
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from metadata.generated.schema.api.services.createDatabaseService import CreateDatabaseServiceRequest
from metadata.generated.schema.entity.data.table import DataType, TableType
from metadata.generated.schema.metadataIngestion.workflow import OpenMetadataWorkflowConfig
import pytest
import yaml

from openmetadata_duckdb.source import DuckDBSource

CONFIGS = Path(__file__).parents[1] / "configs"


@pytest.fixture
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse_dev.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("create schema raw; create schema marts; create schema test_failures")
        con.execute(
            "create table raw.bmrs__mid (settlement_date date, price decimal(18, 3), volume hugeint, "
            "published timestamptz, code varchar, ids integer[], _dlt_load_id varchar not null)"
        )
        con.execute("comment on table raw.bmrs__mid is 'Market index data'")
        con.execute("create view marts.mart_price as select settlement_date, price from raw.bmrs__mid")
        con.execute("create table test_failures.unique_x (n integer)")
    return path


def source(path: Path, **pipeline: object) -> DuckDBSource:
    config = yaml.safe_load((CONFIGS / "warehouse.yaml").read_text())["source"]
    config["serviceConnection"]["config"]["connectionOptions"]["databasePath"] = str(path)
    config["sourceConfig"]["config"] |= pipeline
    return DuckDBSource.create(config, metadata=object())  # pyright: ignore[reportArgumentType]


def test_registers_the_catalog_schemas_tables_and_views_in_order(warehouse: Path) -> None:
    records = [result.right for result in source(warehouse)._iter()]

    assert [type(r) for r in records] == [
        CreateDatabaseServiceRequest,
        CreateDatabaseRequest,
        CreateDatabaseSchemaRequest,  # marts (test_failures excluded by the config, main empty)
        CreateTableRequest,
        CreateDatabaseSchemaRequest,  # raw
        CreateTableRequest,
    ]
    database = records[1]
    assert database.name.root == "warehouse_dev"  # the catalog name dbt writes as `database`
    view, table = records[3], records[5]
    assert (view.tableType, view.databaseSchema.root) == (TableType.View, "power_desk_warehouse.warehouse_dev.marts")
    assert "select settlement_date, price" in view.schemaDefinition.root.lower()
    assert (table.tableType, table.description.root) == (TableType.Regular, "Market index data")


def test_columns_map_duckdb_types_and_keep_them_as_displayed(warehouse: Path) -> None:
    *_, table = [result.right for result in source(warehouse)._iter()]

    columns = {c.name.root: c for c in table.columns}
    assert {name: c.dataType for name, c in columns.items()} == {
        "settlement_date": DataType.DATE,
        "price": DataType.DECIMAL,
        "volume": DataType.NUMERIC,
        "published": DataType.TIMESTAMPZ,
        "code": DataType.VARCHAR,
        "ids": DataType.ARRAY,
        "_dlt_load_id": DataType.VARCHAR,
    }
    assert (columns["price"].precision, columns["price"].scale) == (18, 3)
    assert (columns["ids"].arrayDataType, columns["ids"].dataTypeDisplay) == (DataType.INT, "INTEGER[]")
    assert columns["code"].dataLength == 1 and [c.ordinalPosition for c in table.columns] == list(range(1, 8))


def test_schema_and_table_filters_apply(warehouse: Path) -> None:
    only_raw = {"schemaFilterPattern": {"includes": ["^raw$"]}, "tableFilterPattern": {"excludes": ["bmrs__mid"]}}
    filtered = source(warehouse, **only_raw)

    assert [type(r.right) for r in filtered._iter()][-1] is CreateDatabaseSchemaRequest


@pytest.mark.parametrize("name", ["warehouse.yaml", "dbt.yaml"])
def test_workflow_configs_are_valid_openmetadata_workflows(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("POWER_DESK_DUCKDB_PATH", "DBT_CATALOG_PATH", "DBT_RUN_RESULTS"):
        monkeypatch.setenv(variable, "/x")
    monkeypatch.setenv("OPENMETADATA_HOST", "http://localhost:8585/api")
    monkeypatch.setenv("OPENMETADATA_JWT_TOKEN", "token")
    text = re.sub(r"\$\{(\w+)\}", lambda m: os.environ[m[1]], (CONFIGS / name).read_text())

    OpenMetadataWorkflowConfig.model_validate(yaml.safe_load(text))


def test_tables_in_the_default_schema_are_registered(tmp_path: Path) -> None:
    path = tmp_path / "scratch.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("create table loose (n integer)")

    schemas = [r.right.name.root for r in source(path)._iter() if isinstance(r.right, CreateDatabaseSchemaRequest)]

    assert schemas == ["main"]
