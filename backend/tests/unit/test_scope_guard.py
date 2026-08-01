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


class TestClarificationMessage:
    def test_lists_tables(self) -> None:
        text = clarification_message(
            schema_context=_SCHEMA,
            allowed_tables=["customers", "orders"],
        )
        assert "customers" in text
        assert "orders" in text
        assert "too broad" in text.lower()
