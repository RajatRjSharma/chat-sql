"""Tests for warehouse-wide catalog overview intent."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.services.catalog_overview import (
    format_catalog_inventory,
    is_catalog_overview_question,
    tables_mentioned_in_question,
)
from app.services.chat_service import ChatService
from app.services.schema_linker import SchemaChunk


def _chunk(table: str) -> SchemaChunk:
    return SchemaChunk(
        content=f"Table: sales.{table}\nColumns:\n  - id: integer",
        table=table,
        schema_name="sales",
        metadata={"table": table, "schema": "sales"},
    )


class TestIsCatalogOverviewQuestion:
    def test_summary_of_db(self) -> None:
        assert is_catalog_overview_question("give me the summary of db") is True
        assert is_catalog_overview_question("give me the summary for the db") is True

    def test_summary_of_the_full_database(self) -> None:
        """Production demo phrasing — intensifier before database."""
        assert (
            is_catalog_overview_question("Give me a summary of the full database.")
            is True
        )
        assert is_catalog_overview_question("summary of the entire schema") is True
        assert is_catalog_overview_question("overview of the complete warehouse") is True
        assert is_catalog_overview_question("give me summary of full db") is True

    def test_overview_phrasing_variants(self) -> None:
        assert is_catalog_overview_question("summary of this database") is True
        assert is_catalog_overview_question("summarize the database") is True
        assert is_catalog_overview_question("summarise my warehouse") is True
        assert is_catalog_overview_question("describe the database") is True
        assert is_catalog_overview_question("what's in the db") is True
        assert is_catalog_overview_question("database overview") is True
        assert is_catalog_overview_question("show me all the tables") is True
        assert is_catalog_overview_question("list every table") is True
        assert is_catalog_overview_question("list the tables") is True
        assert is_catalog_overview_question("row counts for every table") is True

    def test_all_tables(self) -> None:
        assert is_catalog_overview_question("list all tables") is True

    def test_all_tables_predicate_is_not_overview(self) -> None:
        assert is_catalog_overview_question("all tables have null amounts") is False

    def test_how_many_tables(self) -> None:
        assert is_catalog_overview_question("how many tables are in the warehouse") is True

    def test_join_question_is_false(self) -> None:
        assert (
            is_catalog_overview_question(
                "total sales by region joining orders and customers"
            )
            is False
        )

    def test_invoice_amounts_is_not_overview(self) -> None:
        assert (
            is_catalog_overview_question("what are the amounts ranging in invoices")
            is False
        )

    def test_related_tables_ask_is_not_overview(self) -> None:
        assert is_catalog_overview_question("show tables related to invoices") is False
        assert is_catalog_overview_question("list tables that have amount columns") is False
        assert is_catalog_overview_question("show tables linked to invoices") is False
        assert is_catalog_overview_question("tables associated with orders") is False
        assert is_catalog_overview_question("inventory of tables having data") is True


class TestTablesMentionedInQuestion:
    def test_invoices_mention(self) -> None:
        names = tables_mentioned_in_question(
            "what are the amounts ranging in invoices",
            ["orders", "invoices", "invoice_lines", "customers"],
        )
        assert names == ["invoices"]

    def test_invoice_singular_links_invoices_table(self) -> None:
        names = tables_mentioned_in_question(
            "sum amount on invoice",
            ["orders", "invoices", "invoice_lines", "customers"],
        )
        # Exact/stem table wins over compound segments (invoice_lines).
        assert "invoices" in names
        assert names[0] == "invoices"

    def test_invoice_lines_explicit(self) -> None:
        names = tables_mentioned_in_question(
            "sum amount on invoice_lines",
            ["orders", "invoices", "invoice_lines", "customers"],
        )
        assert "invoice_lines" in names

    def test_no_false_match_on_trivia(self) -> None:
        names = tables_mentioned_in_question(
            "height of Burj Khalifa",
            ["orders", "customers"],
        )
        assert names == []

    def test_database_stopword_does_not_match_trap_table(self) -> None:
        names = tables_mentioned_in_question(
            "query the database for orders",
            ["orders", "database_metrics", "amount_limits"],
        )
        assert names == ["orders"]
        assert "database_metrics" not in names
        assert "amount_limits" not in names

    def test_channel_prefers_channels_over_campaign_channels(self) -> None:
        names = tables_mentioned_in_question(
            "Total revenue by region and channel",
            ["channels", "campaign_channels", "regions", "orders"],
        )
        assert "channels" in names
        assert "regions" in names
        assert "campaign_channels" not in names


class TestColumnConceptLinking:
    def test_revenue_by_region_links_customers_and_orders(self) -> None:
        from app.services.catalog_overview import link_tables_for_question
        from app.services.schema_linker import SchemaChunk

        chunks = [
            SchemaChunk(
                content=(
                    "Table: sales.customers\nColumns:\n"
                    "  - customer_id: integer\n  - region: varchar"
                ),
                table="customers",
                schema_name="sales",
            ),
            SchemaChunk(
                content=(
                    "Table: sales.orders\nColumns:\n"
                    "  - order_id: integer\n  - amount: numeric\n"
                    "  - channel_id: integer"
                ),
                table="orders",
                schema_name="sales",
            ),
            SchemaChunk(
                content=(
                    "Table: sales.channels\nColumns:\n"
                    "  - channel_id: integer\n  - name: varchar"
                ),
                table="channels",
                schema_name="sales",
            ),
            SchemaChunk(
                content=(
                    "Table: sales.regions\nColumns:\n"
                    "  - region_id: integer\n  - name: varchar"
                ),
                table="regions",
                schema_name="sales",
            ),
            SchemaChunk(
                content=(
                    "Table: sales.currencies\nColumns:\n"
                    "  - currency_code: char\n  - name: varchar"
                ),
                table="currencies",
                schema_name="sales",
            ),
        ]
        linked = link_tables_for_question(
            "Total revenue by region and channel",
            chunks,
        )
        assert "customers" in linked  # region column
        assert "orders" in linked  # amount via revenue synonym
        assert "channels" in linked
        assert "regions" in linked
        assert "currencies" not in linked

    def test_suggested_hops_deepens_for_multi_dim(self) -> None:
        from app.services.catalog_overview import suggested_expand_hops

        assert suggested_expand_hops(1, 1) == 1
        assert suggested_expand_hops(2, 1) == 2
        assert suggested_expand_hops(3, 0) == 2


class TestFormatCatalogInventory:
    def test_lists_every_table(self) -> None:
        text = format_catalog_inventory(
            schema_name="sales",
            table_names=["orders", "customers", "z_misc"],
        )
        assert "3 tables" in text
        assert "- sales.orders" in text
        assert "- sales.customers" in text
        assert "- sales.z_misc" in text
        assert "EVERY table" in text


class TestBuildPreparedCatalogOverview:
    def test_allowlists_all_tables_with_inventory_context(self) -> None:
        chunks = [_chunk(f"t{i}") for i in range(20)]
        info = SimpleNamespace(schema_name="sales", connection_url="postgresql://x")
        data_source = SimpleNamespace(
            id=uuid.uuid4(),
            name="Demo",
            db_type="postgres",
            host="localhost",
            port=5432,
            database="wh",
            schema_name="sales",
            is_readonly=True,
        )
        captured: dict[str, str] = {}

        def _fake_graph(*, schema_context: str, client):  # noqa: ANN001
            captured["schema_context"] = schema_context
            return object()

        with patch("app.services.chat_service.build_chat_graph", side_effect=_fake_graph):
            prepared = ChatService._build_prepared(
                ai=object(),  # type: ignore[arg-type]
                data_source=data_source,
                data_source_id=data_source.id,
                question="summary of the database",
                chat_session=SimpleNamespace(session_id=uuid.uuid4()),
                history=[],
                info=info,
                linked_chunks=chunks,
                context_mode="catalog_overview",
            )

        assert prepared["context_mode"] == "catalog_overview"
        assert prepared["source_metadata"]["context_mode"] == "catalog_overview"
        assert len(prepared["state"]["allowed_tables"]) == 20
        assert set(prepared["state"]["allowed_tables"]) == {f"t{i}" for i in range(20)}
        assert "Complete indexed table inventory" in captured["schema_context"]
        assert "- sales.t0" in captured["schema_context"]
        assert "- sales.t19" in captured["schema_context"]
        # Names-only: no per-table DDL dump
        assert "Columns:" not in captured["schema_context"]
