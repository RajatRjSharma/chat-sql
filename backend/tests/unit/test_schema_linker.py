"""Tests for FK neighborhood schema linking."""

from __future__ import annotations

from app.services.schema_linker import (
    SchemaChunk,
    SchemaLinker,
    parse_allowlist_miss_tables,
    parse_fk_edges_from_chunk,
    parse_fk_edges_from_metadata,
    parse_table_from_chunk,
)


def _chunk(
    table: str,
    *,
    schema: str = "sales",
    fks: list[tuple[str, str]] | None = None,
    use_metadata_fks: bool = False,
) -> SchemaChunk:
    lines = [
        f"Table: {schema}.{table}",
        "Columns:",
        "  - id: integer (PK)",
    ]
    meta_fks: list[dict[str, str]] = []
    if fks:
        lines.append("Foreign keys:")
        for col, ref in fks:
            lines.append(f"  - {col} -> {schema}.{ref}.id")
            meta_fks.append(
                {
                    "column": col,
                    "referenced_table": ref,
                    "referenced_column": "id",
                }
            )
    metadata = {
        "schema": schema,
        "table": table,
        "qualified_name": f"{schema}.{table}",
    }
    if use_metadata_fks:
        metadata["foreign_keys"] = meta_fks
    return SchemaChunk(
        content="\n".join(lines),
        table=table,
        schema_name=schema,
        metadata=metadata,
    )


class TestParseHelpers:
    def test_parse_table_from_chunk(self) -> None:
        assert parse_table_from_chunk("Table: sales.orders\nColumns:") == "orders"

    def test_parse_fk_edges_from_chunk(self) -> None:
        content = (
            "Table: sales.orders\n"
            "Foreign keys:\n"
            "  - customer_id -> sales.customers.customer_id\n"
            "  - channel_id -> sales.channels.channel_id\n"
        )
        edges = set(parse_fk_edges_from_chunk(content))
        assert ("orders", "customers") in edges
        assert ("orders", "channels") in edges

    def test_parse_fk_edges_from_metadata(self) -> None:
        edges = parse_fk_edges_from_metadata(
            "orders",
            {
                "foreign_keys": [
                    {
                        "column": "customer_id",
                        "referenced_table": "customers",
                        "referenced_column": "customer_id",
                    }
                ]
            },
        )
        assert edges == [("orders", "customers")]

    def test_parse_allowlist_miss_tables(self) -> None:
        err = "Table 'channels' is not in the allowed table set."
        assert parse_allowlist_miss_tables(err) == ["channels"]


class TestSchemaLinkerExpand:
    def test_expands_one_hop_neighbors(self) -> None:
        orders = _chunk("orders", fks=[("customer_id", "customers"), ("channel_id", "channels")])
        customers = _chunk("customers", fks=[("segment_id", "customer_segments")])
        channels = _chunk("channels")
        segments = _chunk("customer_segments")
        unrelated = _chunk("tickets")

        catalog = [orders, customers, channels, segments, unrelated]
        expanded = SchemaLinker.expand(
            [orders],
            catalog,
            hops=1,
            max_tables=15,
        )
        names = [c.table for c in expanded]
        assert names[0] == "orders"
        assert "customers" in names
        assert "channels" in names
        # 1 hop from orders does not reach customer_segments
        assert "customer_segments" not in names
        assert "tickets" not in names

    def test_two_hops_reaches_grandparent(self) -> None:
        orders = _chunk("orders", fks=[("customer_id", "customers")])
        customers = _chunk("customers", fks=[("segment_id", "customer_segments")])
        segments = _chunk("customer_segments")
        expanded = SchemaLinker.expand(
            [orders],
            [orders, customers, segments],
            hops=2,
            max_tables=15,
        )
        names = {c.table for c in expanded}
        assert names == {"orders", "customers", "customer_segments"}

    def test_respects_max_tables_cap(self) -> None:
        seed = _chunk("orders", fks=[(f"fk{i}", f"t{i}") for i in range(10)])
        catalog = [seed] + [_chunk(f"t{i}") for i in range(10)]
        expanded = SchemaLinker.expand([seed], catalog, hops=1, max_tables=4)
        assert len(expanded) == 4
        assert expanded[0].table == "orders"

    def test_hops_zero_keeps_seeds_only(self) -> None:
        orders = _chunk("orders", fks=[("customer_id", "customers")])
        customers = _chunk("customers")
        expanded = SchemaLinker.expand(
            [orders],
            [orders, customers],
            hops=0,
            max_tables=15,
        )
        assert [c.table for c in expanded] == ["orders"]

    def test_prefers_metadata_fks(self) -> None:
        orders = _chunk(
            "orders",
            fks=[("customer_id", "customers")],
            use_metadata_fks=True,
        )
        customers = _chunk("customers")
        expanded = SchemaLinker.expand(
            [orders],
            [orders, customers],
            hops=1,
            max_tables=15,
        )
        assert {c.table for c in expanded} == {"orders", "customers"}

    def test_merge_chunks_preserves_order_and_cap(self) -> None:
        a = _chunk("orders")
        b = _chunk("customers")
        c = _chunk("channels")
        merged = SchemaLinker.merge_chunks([a], [b, c, a], max_tables=2)
        assert [x.table for x in merged] == ["orders", "customers"]
