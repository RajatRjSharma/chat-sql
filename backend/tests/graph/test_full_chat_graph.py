"""End-to-end LangGraph tests for the full prepare + SQL agent path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.graph.chat_graph import (
    aiter_chat_graph,
    arun_chat_graph,
    build_chat_graph,
    initial_chat_state,
)
from app.graph.nodes import (
    route_after_expand,
    route_after_generate,
    route_after_summarize,
    route_after_validate,
)
from app.graph.retry_policy import (
    needs_allowlist_expand,
    needs_empty_result_retry,
    needs_unanswerable_expand,
)
from app.services.entity_linker import EntityLinkResult
from app.services.intent_router import IntentDecision
from app.services.schema_linker import SchemaChunk
from app.services.scope_guard import OUT_OF_SCOPE_MESSAGE
from app.services.warehouse_executor import QueryResult
from tests.conftest import DEMO_SOURCE_ID


def _chunk(table: str) -> SchemaChunk:
    return SchemaChunk(
        content=(
            f"Table: sales.{table}\n"
            f"Columns:\n  - id: integer\n  - amount: numeric\n  - region: varchar"
        ),
        table=table,
        schema_name="sales",
        metadata={"table": table, "schema": "sales"},
    )


def _ds() -> MagicMock:
    ds = MagicMock()
    ds.id = DEMO_SOURCE_ID
    ds.name = "demo"
    ds.db_type = "postgres"
    ds.host = "localhost"
    ds.port = 5433
    ds.database = "bi_warehouse"
    ds.schema_name = "sales"
    ds.is_readonly = True
    ds.extra_config = {}
    return ds


def _state(**overrides):
    state = initial_chat_state(
        data_source_id=DEMO_SOURCE_ID,
        question="revenue by region",
        connection_url="postgresql://u:p@localhost:5433/bi_warehouse",
        schema_name="sales",
        allowed_tables=[],
        max_attempts=3,
    )
    state.update(overrides)
    return state


class TestFullGraphRoutingPolicy:
    def test_unanswerable_analytics_routes_to_expand(self) -> None:
        state = _state(
            scope="out_of_scope",
            answer=OUT_OF_SCOPE_MESSAGE,
            attempts=1,
            context_mode="rag",
            linked_chunks=[{"content": "x", "table": "orders"}],
            did_expand_retry=False,
        )
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert route_after_generate(state) == "expand"

    def test_allowlist_miss_at_max_routes_to_expand(self) -> None:
        state = _state(
            sql_error="Table 'channels' is not in the allowed table set.",
            attempts=3,
            did_expand_retry=False,
        )
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert route_after_validate(state) == "expand"

    def test_empty_rows_route_to_empty_retry(self) -> None:
        state = _state(
            status="ok",
            sql="SELECT 1",
            rows=[],
            scope="answerable",
            did_empty_retry=False,
            question="total revenue by region",
        )
        assert route_after_summarize(state) == "empty_retry"

    def test_expand_noop_with_answer_ends(self) -> None:
        assert (
            route_after_expand(
                _state(expand_noop=True, answer=OUT_OF_SCOPE_MESSAGE)
            )
            == "end"
        )

    def test_needs_helpers(self) -> None:
        with patch("app.graph.retry_policy.settings") as settings:
            settings.rag_expand_on_retry = True
            assert needs_allowlist_expand(
                {
                    "sql_error": "Table 'x' is not in the allowed table set.",
                    "did_expand_retry": False,
                }
            )
            assert needs_unanswerable_expand(
                {
                    "scope": "out_of_scope",
                    "attempts": 1,
                    "question": "revenue by region",
                    "context_mode": "rag",
                    "linked_chunks": [{"content": "t", "table": "orders"}],
                    "did_expand_retry": False,
                }
            )
            assert needs_empty_result_retry(
                {
                    "status": "ok",
                    "sql": "SELECT 1",
                    "rows": [],
                    "scope": "answerable",
                    "question": "revenue by region",
                    "did_empty_retry": False,
                }
            )


@pytest.mark.asyncio
async def test_full_graph_happy_path_streams_prep_then_sql() -> None:
    """route_intent → link_entities → retrieve_and_link → SQL → summarize."""
    catalog = [_chunk("orders"), _chunk("customers")]
    session = MagicMock()
    stages: list[str] = []

    intent = IntentDecision(
        intent="analytics",
        confidence=0.9,
        reason="metric ask",
        normalized_question="revenue by region",
        source="llm",
    )
    entities = EntityLinkResult(
        tables=("orders", "customers"),
        measures=("amount",),
        dimensions=("region",),
        source="llm",
    )

    with (
        patch(
            "app.graph.prep_nodes.IntentRouter.route",
            return_value=intent,
        ),
        patch(
            "app.graph.prep_nodes.EntityLinker.link",
            return_value=entities,
        ),
        patch(
            "app.graph.prep_nodes.RagService.retrieve_rows",
            new=AsyncMock(return_value=[_chunk("orders")]),
        ),
        patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.graph.nodes.ScopeGuard.assess",
            return_value="answerable",
        ),
        patch(
            "app.graph.nodes.SqlGenerator.generate",
            return_value=(
                "SELECT c.region, SUM(o.amount) AS revenue "
                "FROM sales.orders o JOIN sales.customers c "
                "ON o.customer_id = c.customer_id GROUP BY c.region"
            ),
        ),
        patch(
            "app.graph.nodes.WarehouseExecutor.execute",
            return_value=QueryResult(
                columns=["region", "revenue"],
                rows=[{"region": "North", "revenue": 100}],
                row_count=1,
            ),
        ),
        patch(
            "app.graph.nodes.ResultSummarizer.summarize",
            return_value="North leads with 100.",
        ),
    ):
        graph = build_chat_graph(
            client=MagicMock(),
            session=session,
            data_source_id=DEMO_SOURCE_ID,
            catalog=catalog,
            warehouse_info=MagicMock(schema_name="sales"),
            data_source=_ds(),
        )
        state = _state(question="revenue by region")
        final: dict = {}
        async for kind, *rest in aiter_chat_graph(graph, state):
            if kind == "stage":
                stages.append(str(rest[0]))
            elif kind == "final":
                final = rest[0]

    assert stages[:3] == ["route_intent", "link_entities", "retrieve_and_link"]
    assert "assess_relevance" in stages
    assert "generate_sql" in stages
    assert "validate_sql" in stages
    assert "execute_sql" in stages
    assert "summarize" in stages
    assert final["status"] == "ok"
    assert final["answer"] == "North leads with 100."
    assert final["rows"][0]["region"] == "North"
    assert "orders" in (final.get("allowed_tables") or [])
    assert final.get("intent") == "analytics"
    assert (final.get("schema_context") or "").startswith("Table:")


@pytest.mark.asyncio
async def test_full_graph_out_of_scope_skips_sql() -> None:
    catalog = [_chunk("orders")]
    intent = IntentDecision(
        intent="out_of_scope",
        confidence=0.95,
        reason="trivia",
        normalized_question="height of burj",
        source="llm",
    )
    with (
        patch("app.graph.prep_nodes.IntentRouter.route", return_value=intent),
        patch("app.graph.prep_nodes.EntityLinker.link") as link,
        patch(
            "app.graph.prep_nodes.RagService.retrieve_rows",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[]),
        ),
        patch("app.graph.nodes.SqlGenerator.generate") as generate,
        patch("app.graph.nodes.WarehouseExecutor.execute") as execute,
    ):
        graph = build_chat_graph(
            client=MagicMock(),
            session=MagicMock(),
            data_source_id=DEMO_SOURCE_ID,
            catalog=catalog,
            warehouse_info=MagicMock(schema_name="sales"),
            data_source=_ds(),
        )
        final = await arun_chat_graph(
            graph,
            _state(question="What is the height of the Burj Khalifa?"),
        )

    link.assert_not_called()
    generate.assert_not_called()
    execute.assert_not_called()
    assert final["scope"] == "out_of_scope"
    assert final["status"] == "ok"
    assert final["sql"] is None
    assert "connected warehouse" in (final.get("answer") or "").lower()


@pytest.mark.asyncio
async def test_full_graph_empty_result_retries_once() -> None:
    catalog = [_chunk("orders")]
    intent = IntentDecision(
        intent="analytics",
        confidence=0.9,
        reason="metric",
        normalized_question="revenue by region",
        source="llm",
    )
    generate = MagicMock(
        side_effect=[
            "SELECT amount FROM sales.orders WHERE 1=0",
            "SELECT amount FROM sales.orders WHERE region = 'North'",
        ]
    )
    execute = MagicMock(
        side_effect=[
            QueryResult(columns=["amount"], rows=[], row_count=0),
            QueryResult(
                columns=["amount"],
                rows=[{"amount": 42}],
                row_count=1,
            ),
        ]
    )
    with (
        patch("app.graph.prep_nodes.IntentRouter.route", return_value=intent),
        patch(
            "app.graph.prep_nodes.EntityLinker.link",
            return_value=EntityLinkResult(tables=("orders",), source="fallback"),
        ),
        patch(
            "app.graph.prep_nodes.RagService.retrieve_rows",
            new=AsyncMock(return_value=[_chunk("orders")]),
        ),
        patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[]),
        ),
        patch("app.graph.nodes.ScopeGuard.assess", return_value="answerable"),
        patch("app.graph.nodes.SqlGenerator.generate", generate),
        patch("app.graph.nodes.WarehouseExecutor.execute", execute),
        patch(
            "app.graph.nodes.ResultSummarizer.summarize",
            return_value="Revenue is 42.",
        ),
    ):
        graph = build_chat_graph(
            client=MagicMock(),
            session=MagicMock(),
            data_source_id=DEMO_SOURCE_ID,
            catalog=catalog,
            warehouse_info=MagicMock(schema_name="sales"),
            data_source=_ds(),
        )
        final = await arun_chat_graph(graph, _state(question="revenue by region"))

    assert generate.call_count == 2
    assert execute.call_count == 2
    assert final["status"] == "ok"
    assert final["rows"] == [{"amount": 42}]
    assert final["answer"] == "Revenue is 42."
    assert final.get("did_empty_retry") is True


@pytest.mark.asyncio
async def test_full_graph_catalog_overview_skips_entity_linker() -> None:
    catalog = [_chunk("orders"), _chunk("customers"), _chunk("channels")]
    intent = IntentDecision(
        intent="catalog_overview",
        confidence=0.92,
        reason="db summary",
        normalized_question="summary for the database",
        source="llm",
    )
    with (
        patch("app.graph.prep_nodes.IntentRouter.route", return_value=intent),
        patch("app.graph.prep_nodes.EntityLinker.link") as link,
        patch(
            "app.graph.prep_nodes.RagService.retrieve_rows",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.graph.prep_nodes.RagService.fetch_chunks_by_tables",
            new=AsyncMock(return_value=[]),
        ),
        patch("app.graph.nodes.ScopeGuard.assess", return_value="answerable"),
        patch(
            "app.graph.nodes.SqlGenerator.generate",
            return_value="SELECT id FROM sales.orders LIMIT 1",
        ),
        patch(
            "app.graph.nodes.WarehouseExecutor.execute",
            return_value=QueryResult(
                columns=["id"],
                rows=[{"id": 1}],
                row_count=1,
            ),
        ),
        patch(
            "app.graph.nodes.ResultSummarizer.summarize",
            return_value="Catalog lists orders.",
        ),
    ):
        graph = build_chat_graph(
            client=MagicMock(),
            session=MagicMock(),
            data_source_id=uuid4(),
            catalog=catalog,
            warehouse_info=MagicMock(schema_name="sales"),
            data_source=_ds(),
        )
        final = await arun_chat_graph(
            graph, _state(question="SUMMARY FOR THE DB")
        )

    link.assert_not_called()
    assert final.get("overview") is True
    assert final.get("intent") == "catalog_overview"
    assert final.get("context_mode") == "catalog_overview"
    assert final["status"] == "ok"
    assert final["answer"] == "Catalog lists orders."
    assert set(final.get("allowed_tables") or []) >= {"orders", "customers", "channels"}
