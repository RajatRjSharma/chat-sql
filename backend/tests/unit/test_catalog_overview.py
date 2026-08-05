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

    def test_all_tables(self) -> None:
        assert is_catalog_overview_question("list all tables") is True

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


class TestTablesMentionedInQuestion:
    def test_invoices_mention(self) -> None:
        names = tables_mentioned_in_question(
            "what are the amounts ranging in invoices",
            ["orders", "invoices", "invoice_lines", "customers"],
        )
        assert names == ["invoices"]

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
