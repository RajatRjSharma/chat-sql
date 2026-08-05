"""Rich offline catalog fixture mirroring sales_extended (DDL + FK metadata).

Used by eval so linking/expand recall matches production chunk shapes.
"""

from __future__ import annotations

from app.services.schema_chunker import (
    CHUNK_KIND_CATALOG,
    CHUNK_KIND_RELATIONSHIPS,
    CHUNK_KIND_TABLE,
    SYNTHETIC_CATALOG_TABLE,
    SYNTHETIC_RELATIONSHIPS_TABLE,
)
from app.services.schema_linker import SchemaChunk

# table -> (column DDL lines, foreign_keys metadata list)
_TABLE_SPECS: dict[str, tuple[str, list[dict[str, str]]]] = {
    "customers": (
        "  - customer_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - region: varchar\n"
        "  - territory_id: integer\n"
        "  - segment_id: integer",
        [
            {
                "column": "territory_id",
                "referenced_table": "territories",
                "referenced_column": "territory_id",
            },
            {
                "column": "segment_id",
                "referenced_table": "customer_segments",
                "referenced_column": "segment_id",
            },
        ],
    ),
    "orders": (
        "  - order_id: integer (PK)\n"
        "  - customer_id: integer\n"
        "  - product_id: integer\n"
        "  - amount: numeric\n"
        "  - channel_id: integer\n"
        "  - order_date: date\n"
        "  - status: varchar",
        [
            {
                "column": "customer_id",
                "referenced_table": "customers",
                "referenced_column": "customer_id",
            },
            {
                "column": "product_id",
                "referenced_table": "products",
                "referenced_column": "product_id",
            },
            {
                "column": "channel_id",
                "referenced_table": "channels",
                "referenced_column": "channel_id",
            },
        ],
    ),
    "order_lines": (
        "  - order_line_id: bigint (PK)\n"
        "  - order_id: integer\n"
        "  - product_id: integer\n"
        "  - qty: integer\n"
        "  - unit_price: numeric\n"
        "  - line_amount: numeric",
        [
            {
                "column": "order_id",
                "referenced_table": "orders",
                "referenced_column": "order_id",
            },
        ],
    ),
    "products": (
        "  - product_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - category: varchar\n"
        "  - price: numeric\n"
        "  - category_id: integer",
        [],
    ),
    "invoices": (
        "  - invoice_id: integer (PK)\n"
        "  - customer_id: integer\n"
        "  - total_amount: numeric\n"
        "  - status: varchar",
        [
            {
                "column": "customer_id",
                "referenced_table": "customers",
                "referenced_column": "customer_id",
            },
        ],
    ),
    "invoice_lines": (
        "  - invoice_line_id: integer (PK)\n"
        "  - invoice_id: integer\n"
        "  - line_amount: numeric",
        [
            {
                "column": "invoice_id",
                "referenced_table": "invoices",
                "referenced_column": "invoice_id",
            },
        ],
    ),
    "payments": (
        "  - payment_id: integer (PK)\n"
        "  - order_id: integer\n"
        "  - amount: numeric\n"
        "  - status: varchar",
        [
            {
                "column": "order_id",
                "referenced_table": "orders",
                "referenced_column": "order_id",
            },
        ],
    ),
    "channels": (
        "  - channel_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - code: varchar",
        [],
    ),
    "regions": (
        "  - region_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - code: varchar",
        [],
    ),
    "territories": (
        "  - territory_id: integer (PK)\n"
        "  - name: varchar\n"
        "  - region_id: integer",
        [
            {
                "column": "region_id",
                "referenced_table": "regions",
                "referenced_column": "region_id",
            },
        ],
    ),
    "customer_segments": (
        "  - segment_id: integer (PK)\n"
        "  - code: varchar\n"
        "  - name: varchar",
        [],
    ),
    "campaign_channels": (
        "  - campaign_id: integer\n"
        "  - channel_id: integer",
        [
            {
                "column": "channel_id",
                "referenced_table": "channels",
                "referenced_column": "channel_id",
            },
        ],
    ),
    "database_metrics": (
        "  - metric_id: integer (PK)\n"
        "  - name: varchar",
        [],
    ),
    "amount_limits": (
        "  - limit_id: integer (PK)\n"
        "  - cap_value: numeric",
        [],
    ),
}

EVAL_CATALOG_TABLES: tuple[str, ...] = tuple(_TABLE_SPECS.keys())


def build_table_chunk(table: str, *, schema: str = "sales") -> SchemaChunk:
    if table == SYNTHETIC_CATALOG_TABLE:
        names = "\n".join(f"- {schema}.{t}" for t in EVAL_CATALOG_TABLES)
        return SchemaChunk(
            content=(
                f"Database catalog / schema inventory for {schema} "
                f"({len(EVAL_CATALOG_TABLES)} tables).\n"
                "Include EVERY table below when answering overview / all-tables questions.\n"
                f"Tables:\n{names}"
            ),
            table=table,
            schema_name=schema,
            metadata={"chunk_kind": CHUNK_KIND_CATALOG, "table": table, "schema": schema},
        )
    if table == SYNTHETIC_RELATIONSHIPS_TABLE:
        return SchemaChunk(
            content=(
                f"Schema relationship graph / ER overview for {schema}.\n"
                "Relationships:\n"
                f"- {schema}.orders.customer_id -> {schema}.customers.customer_id\n"
                f"- {schema}.orders.channel_id -> {schema}.channels.channel_id"
            ),
            table=table,
            schema_name=schema,
            metadata={
                "chunk_kind": CHUNK_KIND_RELATIONSHIPS,
                "table": table,
                "schema": schema,
            },
        )

    cols, fks = _TABLE_SPECS[table]
    fk_lines = ""
    if fks:
        fk_lines = "\nForeign keys:\n" + "\n".join(
            f"  - {fk['column']} -> {schema}.{fk['referenced_table']}.{fk['referenced_column']}"
            for fk in fks
        )
    return SchemaChunk(
        content=f"Table: {schema}.{table}\nColumns:\n{cols}{fk_lines}",
        table=table,
        schema_name=schema,
        metadata={
            "chunk_kind": CHUNK_KIND_TABLE,
            "table": table,
            "schema": schema,
            "foreign_keys": [
                {**fk, "from_table": table} for fk in fks
            ],
        },
    )


def build_eval_catalog(*, include_synthetic: bool = True) -> list[SchemaChunk]:
    chunks = [build_table_chunk(t) for t in EVAL_CATALOG_TABLES]
    if include_synthetic:
        chunks.append(build_table_chunk(SYNTHETIC_CATALOG_TABLE))
        chunks.append(build_table_chunk(SYNTHETIC_RELATIONSHIPS_TABLE))
    return chunks
