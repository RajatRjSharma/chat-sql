"""Tests for schema chunking."""

from __future__ import annotations

from app.services.schema_chunker import chunk_table, chunk_tables
from app.services.schema_introspection import ColumnInfo, ForeignKeyInfo, TableInfo


def _sample_table() -> TableInfo:
    return TableInfo(
        schema_name="sales",
        table_name="orders",
        columns=[
            ColumnInfo(name="order_id", data_type="integer", is_nullable=False, is_primary_key=True),
            ColumnInfo(name="amount", data_type="numeric", is_nullable=False),
            ColumnInfo(name="customer_id", data_type="integer", is_nullable=False),
        ],
        foreign_keys=[
            ForeignKeyInfo(
                column="customer_id",
                referenced_table="customers",
                referenced_column="customer_id",
            )
        ],
        sample_rows=[{"order_id": 1, "amount": 10.5, "customer_id": 2}],
    )


class TestSchemaChunker:
    def test_chunk_table_includes_columns_and_fks(self) -> None:
        text = chunk_table(_sample_table())
        assert "Table: sales.orders" in text
        assert "order_id: integer (PK, NOT NULL)" in text
        assert "customer_id -> sales.customers.customer_id" in text
        assert "Sample rows:" in text

    def test_chunk_table_includes_warehouse_header(self) -> None:
        text = chunk_table(
            _sample_table(),
            warehouse_header="Warehouse: PostgreSQL | Dialect: postgres",
        )
        assert text.startswith("Warehouse: PostgreSQL")
        assert "Table: sales.orders" in text

    def test_chunk_tables_metadata(self) -> None:
        chunks = chunk_tables(
            [_sample_table()],
            engine_meta={"db_type": "postgres", "engine": "PostgreSQL", "sql_dialect": "postgres"},
        )
        assert len(chunks) == 1
        content, metadata = chunks[0]
        assert metadata["qualified_name"] == "sales.orders"
        assert metadata["engine"] == "PostgreSQL"
        assert "sales.orders" in content
