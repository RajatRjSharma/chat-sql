"""Tests for LangGraph routing and nodes with mocked services."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.graph.chat_graph import build_chat_graph, initial_chat_state, run_chat_graph
from app.graph.nodes import (
    assess_relevance_node,
    finalize_failure_node,
    generate_sql_node,
    route_after_execute,
    route_after_generate,
    route_after_relevance,
    route_after_validate,
    summarize_node,
    validate_sql_node,
)
from app.services.scope_guard import (
    EMPTY_RESULT_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    PLANNING_FAILED_MESSAGE,
)
from app.services.warehouse_executor import QueryResult
from tests.conftest import DEMO_SOURCE_ID


def _base_state(**overrides):
    state = initial_chat_state(
        data_source_id=DEMO_SOURCE_ID,
        question="sales by region",
        connection_url="postgresql://u:p@localhost:5433/bi_warehouse",
        schema_name="sales",
        allowed_tables=["orders", "customers"],
        max_attempts=3,
    )
    state.update(overrides)
    return state


class TestRouting:
    def test_validate_ok_routes_to_execute(self) -> None:
        assert route_after_validate(_base_state(sql_error=None, attempts=1)) == "execute"

    def test_validate_error_retries(self) -> None:
        assert route_after_validate(_base_state(sql_error="bad", attempts=1)) == "retry"

    def test_validate_error_fails_at_max(self) -> None:
        assert route_after_validate(_base_state(sql_error="bad", attempts=3)) == "fail"

    def test_execute_error_retries(self) -> None:
        assert route_after_execute(_base_state(sql_error="boom", attempts=1)) == "retry"

    def test_execute_ok_summarizes(self) -> None:
        assert route_after_execute(_base_state(sql_error=None, attempts=1)) == "summarize"

    def test_relevance_out_of_scope_ends(self) -> None:
        assert route_after_relevance(_base_state(scope="out_of_scope")) == "end"

    def test_relevance_clarify_ends(self) -> None:
        assert route_after_relevance(_base_state(scope="needs_clarification")) == "end"

    def test_relevance_answerable_generates(self) -> None:
        assert route_after_relevance(_base_state(scope="answerable")) == "generate"

    def test_generate_unanswerable_ends(self) -> None:
        assert (
            route_after_generate(
                _base_state(scope="out_of_scope", answer=OUT_OF_SCOPE_MESSAGE)
            )
            == "end"
        )


class TestNodes:
    def test_validate_sql_success(self) -> None:
        state = _base_state(sql="SELECT amount FROM sales.orders")
        out = validate_sql_node(state)
        assert out["sql_error"] is None
        assert "SELECT" in out["sql"]

    def test_validate_sql_failure(self) -> None:
        state = _base_state(sql="DELETE FROM sales.orders")
        out = validate_sql_node(state)
        assert out["sql_error"]

    def test_generate_sql_increments_attempts(self) -> None:
        mock_client = MagicMock()
        with patch(
            "app.graph.nodes.SqlGenerator.generate",
            return_value="SELECT 1",
        ):
            out = generate_sql_node(_base_state(attempts=0), client=mock_client)
        assert out["attempts"] == 1
        assert out["sql"] == "SELECT 1"

    def test_generate_sql_unanswerable_marker(self) -> None:
        with patch(
            "app.graph.nodes.SqlGenerator.generate",
            return_value="UNANSWERABLE",
        ):
            out = generate_sql_node(_base_state(attempts=0))
        assert out["scope"] == "out_of_scope"
        assert out["status"] == "ok"
        # Planning failure gets its own copy, not the scope refusal text.
        assert out["answer"] == PLANNING_FAILED_MESSAGE
        assert out["answer"] != OUT_OF_SCOPE_MESSAGE
        assert out["sql"] is None

    def test_assess_relevance_refuses(self) -> None:
        with patch(
            "app.graph.nodes.ScopeGuard.assess",
            return_value="out_of_scope",
        ):
            out = assess_relevance_node(
                _base_state(question="height of Burj Khalifa", schema_context="orders"),
            )
        assert out["scope"] == "out_of_scope"
        assert out["answer"] == OUT_OF_SCOPE_MESSAGE
        assert out["status"] == "ok"

    def test_assess_relevance_clarifies(self) -> None:
        with patch(
            "app.graph.nodes.ScopeGuard.assess",
            return_value="needs_clarification",
        ):
            out = assess_relevance_node(
                _base_state(
                    question="summary",
                    schema_context="Table: sales.customers",
                    allowed_tables=["customers"],
                ),
            )
        assert out["scope"] == "needs_clarification"
        assert "too broad" in out["answer"].lower()
        assert "customers" in out["answer"].lower()
        assert out["status"] == "ok"

    def test_summarize_empty_rows_skips_llm(self) -> None:
        with patch("app.graph.nodes.ResultSummarizer.summarize") as summarize:
            out = summarize_node(_base_state(columns=["x"], rows=[]))
        summarize.assert_not_called()
        assert out["answer"] == EMPTY_RESULT_MESSAGE
        assert out["status"] == "ok"

    def test_finalize_failure(self) -> None:
        out = finalize_failure_node(_base_state(sql_error="nope"))
        assert out["status"] == "failed"
        assert "nope" in out["answer"]


class TestChatGraph:
    def test_happy_path(self) -> None:
        mock_client = MagicMock()
        with (
            patch(
                "app.graph.nodes.ScopeGuard.assess",
                return_value="answerable",
            ),
            patch(
                "app.graph.nodes.SqlGenerator.generate",
                return_value="SELECT c.region, SUM(o.amount) AS total "
                "FROM sales.orders o JOIN sales.customers c "
                "ON o.customer_id = c.customer_id GROUP BY c.region",
            ),
            patch(
                "app.graph.nodes.WarehouseExecutor.execute",
                return_value=QueryResult(
                    columns=["region", "total"],
                    rows=[{"region": "East", "total": 100}],
                    row_count=1,
                ),
            ),
            patch(
                "app.graph.nodes.ResultSummarizer.summarize",
                return_value="East leads with 100.",
            ),
        ):
            graph = build_chat_graph(
                schema_context="Table: sales.orders\nColumns:\n  - amount: numeric",
                client=mock_client,
            )
            final = run_chat_graph(graph, _base_state())

        assert final["status"] == "ok"
        assert final["answer"] == "East leads with 100."
        assert final["rows"][0]["region"] == "East"

    def test_out_of_scope_skips_sql(self) -> None:
        mock_client = MagicMock()
        with (
            patch(
                "app.graph.nodes.ScopeGuard.assess",
                return_value="out_of_scope",
            ),
            patch("app.graph.nodes.SqlGenerator.generate") as generate,
            patch("app.graph.nodes.WarehouseExecutor.execute") as execute,
        ):
            graph = build_chat_graph(
                schema_context="Table: sales.orders",
                client=mock_client,
            )
            final = run_chat_graph(
                graph,
                _base_state(question="What is the height of Burj Khalifa?"),
            )

        generate.assert_not_called()
        execute.assert_not_called()
        assert final["status"] == "ok"
        assert final["scope"] == "out_of_scope"
        assert "connected warehouse" in final["answer"].lower()
        assert final["sql"] is None

    def test_retry_then_success(self) -> None:
        mock_client = MagicMock()
        generate = MagicMock(
            side_effect=[
                "DELETE FROM sales.orders",
                "SELECT amount FROM sales.orders",
            ]
        )
        with (
            patch("app.graph.nodes.ScopeGuard.assess", return_value="answerable"),
            patch("app.graph.nodes.SqlGenerator.generate", generate),
            patch(
                "app.graph.nodes.WarehouseExecutor.execute",
                return_value=QueryResult(columns=["amount"], rows=[{"amount": 1}], row_count=1),
            ),
            patch("app.graph.nodes.ResultSummarizer.summarize", return_value="ok"),
        ):
            graph = build_chat_graph(schema_context="Table: sales.orders", client=mock_client)
            final = run_chat_graph(graph, _base_state())

        assert final["status"] == "ok"
        assert final["attempts"] == 2

    def test_max_retries_fails(self) -> None:
        mock_client = MagicMock()
        with (
            patch("app.graph.nodes.ScopeGuard.assess", return_value="answerable"),
            patch(
                "app.graph.nodes.SqlGenerator.generate",
                return_value="DELETE FROM sales.orders",
            ),
        ):
            graph = build_chat_graph(schema_context="Table: sales.orders", client=mock_client)
            final = run_chat_graph(graph, _base_state(max_attempts=2))

        assert final["status"] == "failed"
        assert final["attempts"] == 2

    def test_empty_result_deterministic_message(self) -> None:
        mock_client = MagicMock()
        with (
            patch("app.graph.nodes.ScopeGuard.assess", return_value="answerable"),
            patch(
                "app.graph.nodes.SqlGenerator.generate",
                return_value="SELECT amount FROM sales.orders WHERE 1=0",
            ),
            patch(
                "app.graph.nodes.WarehouseExecutor.execute",
                return_value=QueryResult(columns=["amount"], rows=[], row_count=0),
            ),
            patch("app.graph.nodes.ResultSummarizer.summarize") as summarize,
        ):
            graph = build_chat_graph(schema_context="Table: sales.orders", client=mock_client)
            final = run_chat_graph(graph, _base_state())

        summarize.assert_not_called()
        assert final["status"] == "ok"
        assert final["answer"] == EMPTY_RESULT_MESSAGE
