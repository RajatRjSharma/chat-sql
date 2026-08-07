"""Unit tests for warehouse scope guard."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.scope_guard import (
    ScopeGuard,
    clarification_message,
)

_SCHEMA = """\
Table: sales.customers
Columns:
  - customer_id: integer
  - name: text
  - region: text
Table: sales.orders
Columns:
  - order_id: integer
  - amount: numeric
Table: sales.products
Columns:
  - product_id: integer
  - name: text
"""


class TestScopeGuardParse:
    def test_answerable(self) -> None:
        assert ScopeGuard.parse_decision("ANSWERABLE") == "answerable"

    def test_out_of_scope(self) -> None:
        assert ScopeGuard.parse_decision("OUT_OF_SCOPE") == "out_of_scope"

    def test_needs_clarification(self) -> None:
        assert ScopeGuard.parse_decision("NEEDS_CLARIFICATION") == "needs_clarification"

    def test_noisy_out_of_scope(self) -> None:
        assert ScopeGuard.parse_decision("out_of_scope\nextra") == "out_of_scope"

    def test_default_answerable_when_unclear(self) -> None:
        assert ScopeGuard.parse_decision("maybe?") == "answerable"

    def test_output_and_outlier_are_not_out_of_scope(self) -> None:
        assert ScopeGuard.parse_decision("OUTPUT") == "answerable"
        assert ScopeGuard.parse_decision("OUTLIER") == "answerable"
        assert ScopeGuard.parse_decision("NEED MORE") == "answerable"

    def test_natural_language_labels_still_parse(self) -> None:
        assert ScopeGuard.parse_decision("Out of scope.") == "out_of_scope"
        assert ScopeGuard.parse_decision("OUT_OF_SCOPE - trivia") == "out_of_scope"
        assert (
            ScopeGuard.parse_decision("Needs clarification") == "needs_clarification"
        )


class TestUnanswerableMarker:
    def test_plain(self) -> None:
        assert ScopeGuard.is_unanswerable_marker("UNANSWERABLE") is True

    def test_fenced(self) -> None:
        assert ScopeGuard.is_unanswerable_marker("```\nUNANSWERABLE\n```") is True

    def test_sql_not_marker(self) -> None:
        assert ScopeGuard.is_unanswerable_marker("SELECT 1") is False


class TestSchemaOverlap:
    def test_customer_matches_customers(self) -> None:
        assert ScopeGuard.has_schema_overlap(
            "what is customer table",
            _SCHEMA,
            ["customers", "orders"],
        )

    def test_sale_matches_sales(self) -> None:
        assert ScopeGuard.has_schema_overlap("whats the sale", _SCHEMA, ["orders"])

    def test_trivia_no_overlap(self) -> None:
        assert not ScopeGuard.has_schema_overlap(
            "height of Burj Khalifa",
            _SCHEMA,
            ["customers", "orders"],
        )


class TestAssessLayered:
    def test_short_sale_question_answerable_without_llm(self) -> None:
        with patch("app.services.scope_guard.get_ai_client") as get_client:
            decision = ScopeGuard.assess(
                question="whats the sale",
                schema_context=_SCHEMA,
                allowed_tables=["customers", "orders", "products"],
            )
        get_client.assert_not_called()
        assert decision == "answerable"

    def test_customer_table_answerable_without_llm(self) -> None:
        with patch("app.services.scope_guard.get_ai_client") as get_client:
            decision = ScopeGuard.assess(
                question="what is customer table",
                schema_context=_SCHEMA,
                allowed_tables=["customers"],
            )
        get_client.assert_not_called()
        assert decision == "answerable"

    def test_summary_alone_needs_clarification(self) -> None:
        with patch("app.services.scope_guard.get_ai_client") as get_client:
            decision = ScopeGuard.assess(
                question="summary",
                schema_context=_SCHEMA,
                allowed_tables=["customers", "orders"],
            )
        get_client.assert_not_called()
        assert decision == "needs_clarification"

    def test_full_db_summary_answerable_via_analytics_hint(self) -> None:
        with patch("app.services.scope_guard.get_ai_client") as get_client:
            decision = ScopeGuard.assess(
                question="give me summary of full db",
                schema_context=_SCHEMA,
                allowed_tables=["customers"],
            )
        get_client.assert_not_called()
        assert decision == "answerable"

    def test_trivia_uses_llm_and_can_refuse(self) -> None:
        mock = MagicMock()
        mock.complete.return_value = "OUT_OF_SCOPE"
        decision = ScopeGuard.assess(
            question="What is the height of Burj Khalifa?",
            schema_context=_SCHEMA,
            allowed_tables=["customers"],
            client=mock,
        )
        mock.complete.assert_called_once()
        assert decision == "out_of_scope"

    def test_follow_up_break_down_by_month_answerable_without_llm(self) -> None:
        """Production smoke: refine prior BI ask — must not hit scope LLM refuse."""
        history = [
            {"role": "user", "content": "Total revenue by region and channel"},
            {"role": "assistant", "content": "North Web Store led."},
        ]
        with patch("app.services.scope_guard.get_ai_client") as get_client:
            decision = ScopeGuard.assess(
                question="Break that down by month",
                schema_context=_SCHEMA,
                allowed_tables=["orders", "customers", "channels"],
                history=history,
            )
        get_client.assert_not_called()
        assert decision == "answerable"

    def test_follow_up_without_history_still_analytics_via_month(self) -> None:
        with patch("app.services.scope_guard.get_ai_client") as get_client:
            decision = ScopeGuard.assess(
                question="Break that down by month",
                schema_context=_SCHEMA,
                allowed_tables=["orders"],
                history=[],
            )
        get_client.assert_not_called()
        assert decision == "answerable"

    def test_break_down_phrase_has_analytics_intent(self) -> None:
        assert ScopeGuard.has_analytics_intent("Break that down by month") is True
        assert ScopeGuard.has_analytics_intent("revenue by month") is True
        assert ScopeGuard.has_analytics_intent("YoY growth in bookings") is True
        assert ScopeGuard.has_analytics_intent("rank customers by spend") is True
        assert ScopeGuard.has_analytics_intent("share of revenue by channel") is True

    def test_soft_bi_words_do_not_bypass_scope_llm(self) -> None:
        """Broad vocabulary drives retries; only strong cues skip the classifier."""
        for question in ("what is the cost of a Tesla", "Messi vs Ronaldo"):
            assert ScopeGuard.has_analytics_intent(question) is True
            assert ScopeGuard.has_warehouse_intent(question) is False

    def test_strong_cues_still_bypass(self) -> None:
        assert ScopeGuard.has_warehouse_intent("give me summary of full db") is True
        assert ScopeGuard.has_warehouse_intent("total amount by month") is True

    def test_trivia_with_soft_word_reaches_llm(self) -> None:
        mock = MagicMock()
        mock.complete.return_value = "OUT_OF_SCOPE"
        decision = ScopeGuard.assess(
            question="what is the cost of a Tesla",
            schema_context=_SCHEMA,
            allowed_tables=["customers"],
            client=mock,
        )
        mock.complete.assert_called_once()
        assert decision == "out_of_scope"


class TestClarificationMessage:
    def test_lists_tables(self) -> None:
        text = clarification_message(
            schema_context=_SCHEMA,
            allowed_tables=["customers", "orders"],
        )
        assert "customers" in text
        assert "orders" in text
        assert "too broad" in text.lower()


class TestAssessRelevanceFollowUp:
    def test_node_passes_history_into_scope(self) -> None:
        from app.graph.chat_graph import initial_chat_state
        from app.graph.nodes import assess_relevance_node
        from tests.conftest import DEMO_SOURCE_ID

        history = [
            {"role": "user", "content": "Total revenue by region and channel"},
            {"role": "assistant", "content": "North led"},
        ]
        state = initial_chat_state(
            data_source_id=DEMO_SOURCE_ID,
            question="Break that down by month",
            connection_url="postgresql://u:p@localhost/db",
            schema_name="sales",
            allowed_tables=["orders"],
            history=history,
        )
        state["schema_context"] = "Table: sales.orders"

        with patch(
            "app.graph.nodes.ScopeGuard.assess",
            return_value="answerable",
        ) as assess:
            out = assess_relevance_node(state)
        assert out["scope"] == "answerable"
        assert assess.call_args.kwargs.get("history") == history
