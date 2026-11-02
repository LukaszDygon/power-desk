"""OpenMetadata custom database connector for a DuckDB file.

OpenMetadata has no DuckDB connector. This one registers the file's schemas, tables and views with their
columns, so other connectors can attach to them: the dbt connector (descriptions, model lineage, tests) and
lineage events. The database is named after the DuckDB catalog (the file name without `.duckdb`), which dbt
writes as each node's `database`, so dbt's nodes resolve to these tables.

Connection options (`serviceConnection.config.connectionOptions`): `databasePath`, the DuckDB file (opened
read-only; DuckDB refuses while another process writes it, so run between writes or on a copy). The
`schemaFilterPattern` and `tableFilterPattern` of the workflow's `sourceConfig` apply.
"""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

import duckdb
from metadata.generated.schema.api.data.createDatabase import CreateDatabaseRequest
from metadata.generated.schema.api.data.createDatabaseSchema import CreateDatabaseSchemaRequest
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from metadata.generated.schema.api.services.createDatabaseService import CreateDatabaseServiceRequest
from metadata.generated.schema.entity.data.table import Column, DataType, TableType
from metadata.generated.schema.entity.services.connections.database.customDatabaseConnection import (
    CustomDatabaseConnection,
)
from metadata.generated.schema.entity.services.databaseService import DatabaseServiceType
from metadata.generated.schema.metadataIngestion.workflow import Source as WorkflowSource
from metadata.ingestion.api.models import Either
from metadata.ingestion.api.steps import InvalidSourceException, Source
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.ingestion.source.database.column_type_parser import ColumnTypeParser
from metadata.utils.filters import filter_by_schema, filter_by_table

# DuckDB types OpenMetadata's ColumnTypeParser does not know, or maps less precisely
DUCKDB_TYPES = {
    "HUGEINT": DataType.NUMERIC,
    "UHUGEINT": DataType.NUMERIC,
    "VARINT": DataType.NUMERIC,
    "UBIGINT": DataType.NUMERIC,
    "UINTEGER": DataType.BIGINT,
    "USMALLINT": DataType.INT,
    "UTINYINT": DataType.SMALLINT,
    "TIMESTAMP WITH TIME ZONE": DataType.TIMESTAMPZ,
    "TIMESTAMP_S": DataType.TIMESTAMP,
    "TIMESTAMP_MS": DataType.TIMESTAMP,
    "TIMESTAMP_NS": DataType.TIMESTAMP,
}
LIST = re.compile(r"^(?P<element>.+)\[\d*\]$")  # INTEGER[] (list) or INTEGER[3] (array)
# OpenMetadata requires a length for these; DuckDB's VARCHAR has none
SIZED = {DataType.CHAR, DataType.VARCHAR, DataType.BINARY, DataType.VARBINARY}

OBJECTS = """
    select schema_name, table_name as name, comment, null as sql from duckdb_tables()
    where database_name = current_database() and not internal and not temporary
    union all
    select schema_name, view_name, comment, sql from duckdb_views()
    where database_name = current_database() and not internal and not temporary
    order by 1, 2
"""
COLUMNS = """
    select schema_name, table_name, column_name, column_index, comment, data_type,
           character_maximum_length, numeric_precision, numeric_scale
    from duckdb_columns() where database_name = current_database() and not internal
    order by schema_name, table_name, column_index
"""
# DuckDB's own schemas (`main` among them) are internal; they count when they hold tables or views
SCHEMAS = """
    select schema_name, comment, internal from duckdb_schemas()
    where database_name = current_database() order by 1
"""


def data_type(duckdb_type: str) -> DataType:
    return DUCKDB_TYPES.get(duckdb_type) or DataType(ColumnTypeParser.get_column_type(duckdb_type))


def column(
    name: str,
    index: int,
    comment: str | None,
    duckdb_type: str,
    length: int | None,
    precision: int | None,
    scale: int | None,
) -> Column:
    """A column of OpenMetadata's type for `duckdb_type`, which it keeps as the displayed type."""
    element = LIST.match(duckdb_type)
    kind = DataType.ARRAY if element else data_type(duckdb_type)
    return Column(
        name=name,
        dataType=kind,
        arrayDataType=data_type(element["element"]) if element else None,
        dataTypeDisplay=duckdb_type,
        dataLength=(length or 1) if kind in SIZED else None,
        precision=precision if kind in (DataType.DECIMAL, DataType.NUMERIC) else None,
        scale=scale if kind in (DataType.DECIMAL, DataType.NUMERIC) else None,
        ordinalPosition=index,
        description=comment or None,
    )


class DuckDBSource(Source):
    """Yields the service, the database, then each schema and its tables and views."""

    def __init__(self, config: WorkflowSource, metadata: OpenMetadata) -> None:
        super().__init__()
        self.config = config
        self.metadata = metadata
        options = config.serviceConnection.root.config.connectionOptions
        self.database_path: str = (options.root if options else {}).get("databasePath", "")
        if not self.database_path:
            raise InvalidSourceException("connectionOptions.databasePath (the DuckDB file) is required")
        self.filters = config.sourceConfig.config

    @classmethod
    def create(cls, config_dict: dict, metadata: OpenMetadata, pipeline_name: str | None = None) -> DuckDBSource:
        config = WorkflowSource.model_validate(config_dict)
        if not isinstance(config.serviceConnection.root.config, CustomDatabaseConnection):
            raise InvalidSourceException(f"expected a CustomDatabaseConnection, got {config.serviceConnection}")
        return cls(config, metadata)

    def prepare(self) -> None:
        """Nothing to prepare: the file is read in `_iter`."""

    def test_connection(self) -> None:
        duckdb.connect(self.database_path, read_only=True).close()

    def close(self) -> None:
        """The file is closed after `_iter`."""

    def _iter(self, *_: Any, **__: Any) -> Iterable[Either]:
        with duckdb.connect(self.database_path, read_only=True) as con:
            (database,) = con.execute("select current_database()").fetchone()
            schemas = con.execute(SCHEMAS).fetchall()
            objects = con.execute(OBJECTS).fetchall()
            columns: dict[tuple[str, str], list[Column]] = {}
            for schema, table, *spec in con.execute(COLUMNS).fetchall():
                columns.setdefault((schema, table), []).append(column(*spec))
        service = self.config.serviceName
        yield Either(
            right=CreateDatabaseServiceRequest(
                name=service,
                serviceType=DatabaseServiceType.CustomDatabase,
                connection=self.config.serviceConnection.root,
            )
        )
        yield Either(right=CreateDatabaseRequest(name=database, service=service))
        holding = {o[0] for o in objects}
        for schema, comment, internal in schemas:
            if (internal and schema not in holding) or filter_by_schema(self.filters.schemaFilterPattern, schema):
                continue
            yield Either(
                right=CreateDatabaseSchemaRequest(name=schema, database=f"{service}.{database}", description=comment)
            )
            schema_fqn = f"{service}.{database}.{schema}"
            for _, name, table_comment, sql in (o for o in objects if o[0] == schema):
                if filter_by_table(self.filters.tableFilterPattern, name):
                    continue
                yield Either(
                    right=CreateTableRequest(
                        name=name,
                        databaseSchema=schema_fqn,
                        tableType=TableType.View if sql else TableType.Regular,
                        columns=columns.get((schema, name), []),
                        description=table_comment or None,
                        schemaDefinition=sql,
                    )
                )
