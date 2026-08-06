"""Solid regression coverage for chat history + multi-turn SQL generation.

Production bug: `for item in history[-5]` indexed a short list → IndexError on
the second question in a session. These cases lock the slice semantics and the
graph path that surfaces history into SqlGenerator.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.graph.chat_graph import build_chat_graph, initial_chat_state, run_chat_graph
from app.graph.nodes import generate_sql_node
from app.services.sql_generator import SqlGenerator
from app.services.warehouse_executor import QueryResult
from tests.conftest import DEMO_SOURCE_ID


def _meta(**extra):
    base = {
        "engine": "PostgreSQL",
        "db_type": "postgres",
        "sql_dialect": "postgres",
        "vendor": "PostgreSQL",
        "database": "bi_warehouse",
        "schema_name": "sales",
        "host": "localhost",
        "port": 5433,
        "is_readonly": True,
        "access_mode": "read_only_select",
        "identifier_quoting": "double_quote",
        "dialect_notes": "ok",
        "embedding_model": "embed",
        "embedding_dimensions": 8,
    }
    base.update(extra)
    return base


def _turns(n: int) -> list[dict[str, str]]:
    """Build n alternating user/assistant history messages."""
    out: list[dict[str, str]] = []
    for i in range(n):
        if i % 2 == 0:
            out.append({"role": "user", "content": f"question {i // 2}"})
        else:
            out.append({"role": "assistant", "content": f"answer {i // 2}"})
    return out


class TestHistoryForPrompt:
    """Unit-level contract for the history helper (slice, never index)."""

    @pytest.mark.parametrize("length", [0, 1, 2, 3, 4, 5, 6, 10])
    def test_all_lengths_safe(self, length: int) -> None:
        history = _turns(length)
        # Must never raise — this is the production IndexError class.
        msgs = SqlGenerator._history_for_prompt(history)
        assert len(msgs) == min(length, 5)
        if length:
            assert all(m["role"] in {"user", "assistant"} for m in msgs)

    def test_none_and_empty(self) -> None:
        assert SqlGenerator._history_for_prompt(None) == []
        assert SqlGenerator._history_for_prompt([]) == []

    def test_keeps_only_last_limit(self) -> None:
        history = _turns(8)
        msgs = SqlGenerator._history_for_prompt(history, limit=5)
        assert len(msgs) == 5
        assert msgs[0]["content"] == "answer 1"
        assert msgs[-1]["content"] == "answer 3"

    def test_skips_malformed_entries(self) -> None:
        history = [
            {"role": "user", "content": "ok"},
            "not-a-dict",  # type: ignore[list-item]
            {"role": "system", "content": "ignore"},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "kept"},
        ]
        msgs = SqlGenerator._history_for_prompt(history)
        assert msgs == [
            {"role": "user", "content": "ok"},
            {"role": "assistant", "content": "kept"},
        ]

    def test_zero_limit(self) -> None:
        assert SqlGenerator._history_for_prompt(_turns(4), limit=0) == []


class TestSqlGeneratorHistoryScenarios:
    """SqlGenerator.generate must accept every realistic history shape."""

    @pytest.mark.parametrize(
        "history",
        [
            None,
            [],
            _turns(1),
            _turns(2),  # production failing case: prior Q+A then new ask
            _turns(4),
            _turns(5),
            _turns(7),
        ],
        ids=[
            "none",
            "empty",
            "one",
            "two_turn_session",
            "four",
            "five",
            "seven_truncates",
        ],
    )
    def test_generate_with_history_shapes(self, history) -> None:
        client = MagicMock()
        client.complete.return_value = "SELECT 1 AS x"
        sql = SqlGenerator.generate(
            question="Total revenue by customer segment",
            schema_context="Table: sales.orders\nTable: sales.customers",
            history=history,
            source_metadata=_meta(),
            client=client,
        )
        assert sql == "SELECT 1 AS x"
        messages = client.complete.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "customer segment" in messages[-1]["content"].lower()
        if history:
            expected = min(len(history), 5)
            # system + history + final user
            assert len(messages) == 1 + expected + 1

    def test_second_session_question_includes_prior_turns(self) -> None:
        """Exact smoke path: Q1 succeeded, Q2 in same session must not crash."""
        client = MagicMock()
        client.complete.return_value = (
            "```sql\nSELECT c.segment, SUM(o.amount) FROM sales.orders o "
            "JOIN sales.customers c ON … GROUP BY 1\n```"
        )
        history = [
            {
                "role": "user",
                "content": "Total revenue by region and channel",
            },
            {
                "role": "assistant",
                "content": "Web Store in North led at $32k.",
            },
        ]
        SqlGenerator.generate(
            question="Total revenue by customer segment",
            schema_context="Table: sales.orders",
            history=history,
            source_metadata=_meta(),
            client=client,
        )
        messages = client.complete.call_args[0][0]
        assert any(
            m.get("role") == "user" and "region and channel" in m.get("content", "")
            for m in messages
        )
        assert any(m.get("role") == "assistant" for m in messages)


class TestGenerateSqlNodeWithHistory:
    """Node wiring must pass history into SqlGenerator without crashing."""

    def test_node_forwards_short_history(self) -> None:
        history = _turns(2)
        client = MagicMock()
        client.complete.return_value = "SELECT segment, SUM(amount) FROM sales.orders"

        state = initial_chat_state(
            data_source_id=DEMO_SOURCE_ID,
            question="Total revenue by customer segment",
            connection_url="postgresql://u:p@localhost/db",
            schema_name="sales",
            allowed_tables=["orders", "customers"],
            history=history,
            source_metadata=_meta(),
        )
        state["schema_context"] = "Table: sales.orders"
        # Real SqlGenerator path (only AI mocked) — catches index-vs-slice bugs.
        out = generate_sql_node(state, client=client)
        assert out.get("sql")
        assert client.complete.called


class TestGraphMultiTurnHistory:
    """Full graph invoke with session history (second-turn smoke)."""

    def test_second_turn_graph_forwards_history(self) -> None:
        history = [
            {"role": "user", "content": "Total revenue by region and channel"},
            {"role": "assistant", "content": "North Web Store led."},
        ]
        client = MagicMock()
        schema_context = (
            "Table: sales.orders (order_id, customer_id, amount)\n"
            "Table: sales.customers (customer_id, segment, region)"
        )

        state = initial_chat_state(
            data_source_id=DEMO_SOURCE_ID,
            question="Total revenue by customer segment",
            connection_url="postgresql://u:p@localhost/db",
            schema_name="sales",
            allowed_tables=["orders", "customers"],
            history=history,
            source_metadata=_meta(),
        )

        with (
            patch(
                "app.graph.nodes.ScopeGuard.assess",
                return_value="answerable",
            ),
            patch(
                "app.graph.nodes.SqlGenerator.generate",
                return_value=(
                    "SELECT c.segment, SUM(o.amount) AS revenue "
                    "FROM sales.orders o "
                    "JOIN sales.customers c ON o.customer_id = c.customer_id "
                    "GROUP BY c.segment"
                ),
            ) as generate,
            patch(
                "app.graph.nodes.WarehouseExecutor.execute",
                return_value=QueryResult(
                    columns=["segment", "revenue"],
                    rows=[{"segment": "Enterprise", "revenue": 1000}],
                    row_count=1,
                ),
            ),
            patch(
                "app.graph.nodes.ResultSummarizer.summarize",
                return_value="Enterprise leads revenue.",
            ),
        ):
            graph = build_chat_graph(schema_context=schema_context, client=client)
            final = run_chat_graph(graph, state)

        assert final["status"] == "ok"
        assert final.get("answer") == "Enterprise leads revenue."
        assert generate.called
        assert generate.call_args.kwargs.get("history") == history

    def test_second_turn_real_sql_generator_no_index_error(self) -> None:
        """End-to-end generate path with short history (the production crash)."""
        history = _turns(2)
        client = MagicMock()
        client.complete.side_effect = [
            (
                "SELECT c.segment, SUM(o.amount) AS revenue "
                "FROM sales.orders o "
                "JOIN sales.customers c ON o.customer_id = c.customer_id "
                "GROUP BY c.segment"
            ),
            "Enterprise leads revenue.",
        ]
        schema_context = (
            "Table: sales.orders\nColumns:\n  - amount: numeric\n"
            "Table: sales.customers\nColumns:\n  - segment: text"
        )
        state = initial_chat_state(
            data_source_id=DEMO_SOURCE_ID,
            question="Total revenue by customer segment",
            connection_url="postgresql://u:p@localhost/db",
            schema_name="sales",
            allowed_tables=["orders", "customers"],
            history=history,
            source_metadata=_meta(),
        )

        with (
            patch("app.graph.nodes.ScopeGuard.assess", return_value="answerable"),
            patch(
                "app.graph.nodes.WarehouseExecutor.execute",
                return_value=QueryResult(
                    columns=["segment", "revenue"],
                    rows=[{"segment": "Enterprise", "revenue": 1000}],
                    row_count=1,
                ),
            ),
        ):
            graph = build_chat_graph(schema_context=schema_context, client=client)
            final = run_chat_graph(graph, state)

        assert final["status"] == "ok"
        assert final.get("sql")
        assert client.complete.call_count >= 1
        # First complete is SQL gen — must have included history turns.
        first_messages = client.complete.call_args_list[0][0][0]
        assert any(m.get("role") == "assistant" for m in first_messages)

    def test_break_down_by_month_follow_up_not_out_of_scope(self) -> None:
        """Production smoke: refine prior BI ask must reach SQL, not refuse."""
        history = [
            {"role": "user", "content": "Total revenue by region and channel"},
            {"role": "assistant", "content": "North Web Store led."},
        ]
        client = MagicMock()
        client.complete.side_effect = [
            (
                "SELECT date_trunc('month', o.order_date) AS month, "
                "c.region, ch.name AS channel, SUM(o.amount) AS revenue "
                "FROM sales.orders o "
                "JOIN sales.customers c ON o.customer_id = c.customer_id "
                "JOIN sales.channels ch ON o.channel_id = ch.channel_id "
                "GROUP BY 1, 2, 3"
            ),
            "Monthly breakdown shows North Web Store still leading.",
        ]
        schema_context = (
            "Table: sales.orders\nColumns:\n  - amount: numeric\n  - order_date: date\n"
            "Table: sales.customers\nColumns:\n  - region: text\n"
            "Table: sales.channels\nColumns:\n  - name: text"
        )
        state = initial_chat_state(
            data_source_id=DEMO_SOURCE_ID,
            question="Break that down by month",
            connection_url="postgresql://u:p@localhost/db",
            schema_name="sales",
            allowed_tables=["orders", "customers", "channels"],
            history=history,
            source_metadata=_meta(
                prior_successful_sql=(
                    "SELECT c.region, ch.name, SUM(o.amount) "
                    "FROM sales.orders o "
                    "JOIN sales.customers c ON o.customer_id = c.customer_id "
                    "JOIN sales.channels ch ON o.channel_id = ch.channel_id "
                    "GROUP BY 1, 2"
                ),
            ),
        )

        with patch(
            "app.graph.nodes.WarehouseExecutor.execute",
            return_value=QueryResult(
                columns=["month", "region", "channel", "revenue"],
                rows=[
                    {
                        "month": "2024-01-01",
                        "region": "North",
                        "channel": "Web Store",
                        "revenue": 500,
                    }
                ],
                row_count=1,
            ),
        ):
            # Real ScopeGuard — must not LLM-refuse this follow-up.
            graph = build_chat_graph(schema_context=schema_context, client=client)
            final = run_chat_graph(graph, state)

        assert final.get("scope") == "answerable"
        assert final["status"] == "ok"
        assert final.get("sql")
        assert "warehouse" not in (final.get("answer") or "").lower()
        assert "out of scope" not in (final.get("answer") or "").lower()
