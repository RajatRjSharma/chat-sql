"""Offline Text-to-SQL eval: schema linking + overview routing + context hygiene.

Inspired by Spider/BIRD schema-linking + component checks, without requiring
live LLM/DB. Run with: `pytest tests/eval -q` or `make eval`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.catalog_overview import (
    is_catalog_overview_question,
    tables_mentioned_in_question,
)
from app.services.chat_service import ChatService
from app.services.schema_chunker import (
    CHUNK_KIND_CATALOG,
    CHUNK_KIND_RELATIONSHIPS,
    CHUNK_KIND_TABLE,
    SYNTHETIC_CATALOG_TABLE,
    SYNTHETIC_RELATIONSHIPS_TABLE,
)
from app.services.schema_linker import SchemaChunk
from app.services.scope_guard import ScopeGuard
from tests.eval.golden_cases import EVAL_CATALOG_TABLES, GOLDEN_CASES, GoldenCase


def _table_chunk(table: str, *, schema: str = "sales") -> SchemaChunk:
    if table == SYNTHETIC_CATALOG_TABLE:
        return SchemaChunk(
            content=(
                "Database catalog / schema inventory for sales (N tables).\n"
                "Include EVERY table below when answering overview / all-tables questions.\n"
                "Tables:\n- sales.invoices\n- sales.orders"
            ),
            table=table,
            schema_name=schema,
            metadata={"chunk_kind": CHUNK_KIND_CATALOG, "table": table},
        )
    if table == SYNTHETIC_RELATIONSHIPS_TABLE:
        return SchemaChunk(
            content=(
                "Schema relationship graph / ER overview for sales.\n"
                "Relationships:\n- sales.orders.customer_id -> sales.customers.customer_id"
            ),
            table=table,
            schema_name=schema,
            metadata={"chunk_kind": CHUNK_KIND_RELATIONSHIPS, "table": table},
        )
    cols = "  - id: integer (PK)\n  - amount: numeric\n  - total_amount: numeric"
    if table == "invoices":
        cols = "  - invoice_id: integer (PK)\n  - total_amount: numeric"
    return SchemaChunk(
        content=f"Table: {schema}.{table}\nColumns:\n{cols}",
        table=table,
        schema_name=schema,
        metadata={"chunk_kind": CHUNK_KIND_TABLE, "table": table, "schema": schema},
    )


def _catalog_chunks() -> list[SchemaChunk]:
    real = [_table_chunk(t) for t in EVAL_CATALOG_TABLES]
    return [
        *real,
        _table_chunk(SYNTHETIC_CATALOG_TABLE),
        _table_chunk(SYNTHETIC_RELATIONSHIPS_TABLE),
    ]


def _capture_schema_context(prepared_mode: str, linked: list[SchemaChunk]) -> str:
    info = SimpleNamespace(schema_name="sales", connection_url="postgresql://x")
    data_source = SimpleNamespace(
        id=uuid4(),
        name="Eval Warehouse",
        db_type="postgres",
        host="localhost",
        port=5432,
        database="bi_warehouse",
        schema_name="sales",
        is_readonly=True,
    )
    captured: dict[str, str] = {}

    def _fake_graph(*, schema_context: str, client):  # noqa: ANN001
        captured["schema_context"] = schema_context
        return object()

    with patch("app.services.chat_service.build_chat_graph", side_effect=_fake_graph):
        prepared = ChatService._build_prepared(
            ai=MagicMock(),
            data_source=data_source,
            data_source_id=data_source.id,
            question="eval",
            chat_session=SimpleNamespace(session_id=uuid4()),
            history=[],
            info=info,
            linked_chunks=linked,
            context_mode=prepared_mode,
        )
    return captured["schema_context"], prepared["state"]["allowed_tables"]


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.id)
def test_overview_routing(case: GoldenCase) -> None:
    assert is_catalog_overview_question(case.question) is case.expect_overview


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.must_include_tables and not c.expect_overview],
    ids=lambda c: c.id,
)
def test_mention_linking_recall(case: GoldenCase) -> None:
    mentioned = tables_mentioned_in_question(case.question, list(EVAL_CATALOG_TABLES))
    for table in case.must_include_tables:
        assert table in mentioned, f"{case.id}: expected mention of {table}, got {mentioned}"
    for table in case.must_exclude_tables:
        assert table not in mentioned


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if c.forbid_in_context],
    ids=lambda c: c.id,
)
def test_context_hygiene_strips_synthetic_overview(case: GoldenCase) -> None:
    """Analytics asks: catalog/ER seed text must not enter SQL schema_context."""
    seeds = [_table_chunk(t) for t in case.rag_seed_tables]
    # Simulate mention + expand result: seeds + required tables' DDL.
    by_name = {c.table: c for c in _catalog_chunks()}
    linked = list(seeds)
    for table in case.must_include_tables:
        chunk = by_name.get(table)
        if chunk and chunk.table not in {c.table for c in linked}:
            linked.append(chunk)

    context, allowed = _capture_schema_context("rag_mentioned", linked)
    for table in case.must_include_tables:
        assert table in allowed
        assert f"sales.{table}" in context or f"Table: sales.{table}" in context
    for needle in case.forbid_in_context:
        assert needle not in context


def test_overview_mode_inventory_lists_all_tables() -> None:
    case = next(c for c in GOLDEN_CASES if c.id == "overview_summary_db")
    linked = _catalog_chunks()
    context, allowed = _capture_schema_context("catalog_overview", linked)
    assert "Complete indexed table inventory" in context
    for table in case.must_include_tables:
        assert table in allowed
        assert f"sales.{table}" in context


def test_scope_gate_analytics_vs_trivia() -> None:
    schema = _table_chunk("orders").content + "\n\n" + _table_chunk("invoices").content
    invoice_case = next(c for c in GOLDEN_CASES if c.id == "invoice_amount_range")
    trivia = next(c for c in GOLDEN_CASES if c.id == "out_of_scope_trivia")

    with patch("app.services.scope_guard.get_ai_client") as get_client:
        get_client.return_value.complete.return_value = "OUT_OF_SCOPE"
        assert (
            ScopeGuard.assess(
                question=invoice_case.question,
                schema_context=schema,
                allowed_tables=["orders", "invoices"],
            )
            == "answerable"
        )
        decision = ScopeGuard.assess(
            question=trivia.question,
            schema_context=schema,
            allowed_tables=["orders", "invoices"],
        )
        assert decision == "out_of_scope"


def test_empty_allowlist_rejects_tables() -> None:
    from app.services.sql_validator import SqlValidationError, SqlValidator

    with pytest.raises(SqlValidationError, match="allowed table set"):
        SqlValidator.validate(
            "SELECT 1 FROM sales.orders",
            allowed_schema="sales",
            allowed_tables=set(),
        )
