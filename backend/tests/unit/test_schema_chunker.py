"""Tests for schema chunking (per-table + overview chunks)."""

from __future__ import annotations

from app.services.schema_chunker import (
    CHUNK_KIND_CATALOG,
    CHUNK_KIND_RELATIONSHIPS,
    CHUNK_KIND_TABLE,
    SYNTHETIC_CATALOG_TABLE,
    SYNTHETIC_RELATIONSHIPS_TABLE,
    chunk_table,
    chunk_tables,
    is_catalog_overview_chunk_metadata,
    is_synthetic_table,
)
from app.services.schema_introspection import ColumnInfo, ForeignKeyInfo, TableInfo


def _sample_table() -> TableInfo:
    return TableInfo(
        schema_name="sales",
        table_name="orders",
        columns=[
            ColumnInfo(
                name="order_id",
                data_type="integer",
                is_nullable=False,
                is_primary_key=True,
            ),
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


def _customers() -> TableInfo:
    return TableInfo(
        schema_name="sales",
        table_name="customers",
        columns=[
            ColumnInfo(
                name="customer_id",
                data_type="integer",
                is_nullable=False,
                is_primary_key=True,
            ),
            ColumnInfo(name="name", data_type="text", is_nullable=False),
        ],
        foreign_keys=[],
        sample_rows=[],
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

    def test_chunk_tables_includes_overview_chunks(self) -> None:
        chunks = chunk_tables(
            [_customers(), _sample_table()],
            engine_meta={
                "db_type": "postgres",
                "engine": "PostgreSQL",
                "sql_dialect": "postgres",
            },
        )
        assert len(chunks) == 4  # 2 tables + catalog + relationships
        kinds = [meta["chunk_kind"] for _, meta in chunks]
        assert kinds.count(CHUNK_KIND_TABLE) == 2
        assert CHUNK_KIND_CATALOG in kinds
        assert CHUNK_KIND_RELATIONSHIPS in kinds

        catalog = next(c for c, m in chunks if m["chunk_kind"] == CHUNK_KIND_CATALOG)
        assert "2 tables" in catalog
        assert "sales.customers" in catalog
        assert "sales.orders" in catalog
        assert "summary of the database" in catalog.lower() or "overview" in catalog.lower()

        rel = next(c for c, m in chunks if m["chunk_kind"] == CHUNK_KIND_RELATIONSHIPS)
        assert "sales.orders.customer_id -> sales.customers.customer_id" in rel
        assert "ER overview" in rel or "relationship graph" in rel.lower()

        catalog_meta = next(m for _, m in chunks if m["chunk_kind"] == CHUNK_KIND_CATALOG)
        assert catalog_meta["table"] == SYNTHETIC_CATALOG_TABLE
        assert is_catalog_overview_chunk_metadata(catalog_meta)

        rel_meta = next(m for _, m in chunks if m["chunk_kind"] == CHUNK_KIND_RELATIONSHIPS)
        assert rel_meta["table"] == SYNTHETIC_RELATIONSHIPS_TABLE
        assert rel_meta["foreign_keys"][0]["from_table"] == "orders"

    def test_chunk_tables_can_skip_overview(self) -> None:
        chunks = chunk_tables([_sample_table()], include_overview_chunks=False)
        assert len(chunks) == 1
        assert chunks[0][1]["chunk_kind"] == CHUNK_KIND_TABLE

    def test_chunk_tables_metadata(self) -> None:
        chunks = chunk_tables(
            [_sample_table()],
            engine_meta={
                "db_type": "postgres",
                "engine": "PostgreSQL",
                "sql_dialect": "postgres",
            },
            include_overview_chunks=False,
        )
        assert len(chunks) == 1
        content, metadata = chunks[0]
        assert metadata["qualified_name"] == "sales.orders"
        assert metadata["engine"] == "PostgreSQL"
        assert metadata["foreign_keys"] == [
            {
                "column": "customer_id",
                "referenced_table": "customers",
                "referenced_column": "customer_id",
            }
        ]
        assert "sales.orders" in content

    def test_synthetic_table_helper(self) -> None:
        assert is_synthetic_table("__catalog__")
        assert is_synthetic_table("__relationships__")
        assert not is_synthetic_table("orders")
        assert not is_synthetic_table(None)
