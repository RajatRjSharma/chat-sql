"""Follow-up detection and client metadata sanitization."""

from __future__ import annotations

from app.services.follow_up import (
    build_retrieval_query,
    last_user_question,
    looks_like_follow_up,
    sanitize_source_metadata_for_client,
    tables_from_sql,
)


class TestLooksLikeFollowUp:
    def test_break_that_down(self) -> None:
        assert (
            looks_like_follow_up(
                "Break that down by month only for the top region.",
                [{"role": "user", "content": "orders by region"}],
            )
            is True
        )

    def test_what_about_named_entity_needs_schema_context(self) -> None:
        """Domain nouns are not hardcoded — the schema decides what's an entity."""
        history = [{"role": "assistant", "content": "North leads"}]
        assert (
            looks_like_follow_up(
                "What about the West region?",
                history,
                schema_tokens={"customers", "region", "orders"},
            )
            is True
        )
        # Without schema context there is no way to tell this from trivia.
        assert looks_like_follow_up("What about the West region?", history) is False

    def test_what_about_with_structural_cue(self) -> None:
        """Grouping / aggregation language is enough on its own, any domain."""
        history = [{"role": "user", "content": "totals by department"}]
        assert looks_like_follow_up("What about by month instead?", history) is True

    def test_schema_tokens_do_not_rescue_trivia(self) -> None:
        assert (
            looks_like_follow_up(
                "What about the height of Burj Khalifa?",
                [{"role": "user", "content": "orders by region"}],
                schema_tokens={"orders", "customers", "region"},
            )
            is False
        )

    def test_soft_what_about_trivia_is_not_follow_up(self) -> None:
        assert (
            looks_like_follow_up(
                "What about the height of Burj Khalifa?",
                [{"role": "user", "content": "orders by region"}],
            )
            is False
        )
        assert (
            looks_like_follow_up(
                "How about writing a Python script?",
                [{"role": "user", "content": "orders by region"}],
            )
            is False
        )

    def test_anaphora_without_bi_is_not_follow_up(self) -> None:
        assert (
            looks_like_follow_up(
                "I think it looks wrong",
                [{"role": "assistant", "content": "North led"}],
            )
            is False
        )
        assert (
            looks_like_follow_up(
                "who is the previous CEO of Apple?",
                [{"role": "user", "content": "orders by region"}],
            )
            is False
        )

    def test_same_breakdown_and_drill_down(self) -> None:
        history = [{"role": "user", "content": "revenue by region"}]
        assert (
            looks_like_follow_up(
                "Same breakdown, but only for Enterprise",
                history,
            )
            is True
        )
        assert looks_like_follow_up("do the same for Q2", history) is True
        assert looks_like_follow_up("drill down by product", history) is True
        assert looks_like_follow_up("just the top 5", history) is True

    def test_implicit_monthly_insights_refinement(self) -> None:
        """Production phrasing: omitted metric inherits the prior analysis."""
        history = [
            {
                "role": "user",
                "content": "Tell me about revenue by regions and sales channels",
            },
            {"role": "assistant", "content": "North Web Store led."},
        ]
        assert looks_like_follow_up("get monthly insights from north", history) is True
        assert (
            looks_like_follow_up(
                "give me insights on monthly revenue for north",
                history,
            )
            is True
        )

    def test_complete_monthly_external_question_is_not_refinement(self) -> None:
        history = [{"role": "user", "content": "revenue by region"}]
        assert looks_like_follow_up("show monthly weather from London", history) is False
        assert (
            looks_like_follow_up(
                "give me insights on monthly weather for London",
                history,
            )
            is False
        )

    def test_independent_question_not_follow_up(self) -> None:
        assert (
            looks_like_follow_up(
                "What is total revenue by customer segment and sales channel?",
                [{"role": "user", "content": "orders by region and month"}],
            )
            is False
        )

    def test_no_history_never_follow_up(self) -> None:
        assert looks_like_follow_up("Break that down by month.", []) is False
        assert looks_like_follow_up("Break that down by month.", None) is False

    def test_independent_new_topic_after_history(self) -> None:
        """Second question that is NOT a follow-up still has history for context."""
        assert (
            looks_like_follow_up(
                "Total revenue by customer segment",
                [
                    {"role": "user", "content": "Total revenue by region and channel"},
                    {"role": "assistant", "content": "North led"},
                ],
            )
            is False
        )

    def test_follow_up_after_successful_turn(self) -> None:
        assert (
            looks_like_follow_up(
                "Break that down by month",
                [
                    {"role": "user", "content": "Total revenue by region and channel"},
                    {"role": "assistant", "content": "North led"},
                ],
            )
            is True
        )


_PRIOR_SQL = """
SELECT r.name, t.name, c.name, SUM(il.amount) AS total_revenue
FROM sales.invoice_lines AS il
JOIN sales.invoices AS i ON il.invoice_id = i.invoice_id
JOIN sales.orders AS o ON i.order_id = o.order_id
JOIN sales.channels AS c ON o.channel_id = c.channel_id
JOIN sales.customers AS cust ON o.customer_id = cust.customer_id
JOIN sales.territories AS t ON cust.territory_id = t.territory_id
GROUP BY r.name, t.name, c.name
"""


class TestTablesFromSql:
    def test_extracts_qualified_tables(self) -> None:
        assert tables_from_sql(_PRIOR_SQL) == [
            "invoice_lines",
            "invoices",
            "orders",
            "channels",
            "customers",
            "territories",
        ]

    def test_unqualified_tables(self) -> None:
        assert tables_from_sql("SELECT * FROM orders JOIN customers ON 1=1") == [
            "orders",
            "customers",
        ]

    def test_none_sql(self) -> None:
        assert tables_from_sql(None) == []


class TestLastUserQuestion:
    def test_returns_latest_user_turn(self) -> None:
        history = [
            {"role": "user", "content": "first ask"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "revenue by territory and channel"},
            {"role": "assistant", "content": "North led"},
        ]
        assert last_user_question(history) == "revenue by territory and channel"

    def test_empty_history(self) -> None:
        assert last_user_question([]) is None


class TestBuildRetrievalQuery:
    def test_follow_up_anchors_prior_question_and_tables(self) -> None:
        """Regression: bare refinements retrieved unrelated chunks."""
        history = [
            {"role": "user", "content": "Total revenue by territory and sales channel"},
            {"role": "assistant", "content": "Midwest Retail led"},
        ]
        query = build_retrieval_query(
            "Break that down by month, only for Midwest.",
            history,
            prior_sql=_PRIOR_SQL,
        )
        assert "Total revenue by territory and sales channel" in query
        assert "Break that down by month" in query
        for table in ("orders", "channels", "customers", "territories"):
            assert table in query

    def test_implicit_monthly_refinement_anchors_prior_context(self) -> None:
        history = [
            {"role": "user", "content": "revenue by region and sales channel"},
            {"role": "assistant", "content": "North Web Store led"},
        ]
        query = build_retrieval_query(
            "get monthly insights from north",
            history,
            prior_sql=_PRIOR_SQL,
        )
        assert "revenue by region and sales channel" in query
        assert "get monthly insights from north" in query
        assert "orders" in query
        assert "channels" in query

        reversed_phrase = build_retrieval_query(
            "give me insights on monthly revenue for north",
            history,
            prior_sql=_PRIOR_SQL,
        )
        assert "revenue by region and sales channel" in reversed_phrase
        assert "orders" in reversed_phrase

    def test_independent_question_unchanged(self) -> None:
        history = [
            {"role": "user", "content": "Total revenue by territory"},
            {"role": "assistant", "content": "Midwest led"},
        ]
        question = "How many open support tickets are there by customer segment?"
        assert build_retrieval_query(question, history, prior_sql=_PRIOR_SQL) == question

    def test_no_history_unchanged(self) -> None:
        assert build_retrieval_query("Break that down by month", []) == (
            "Break that down by month"
        )


class TestSanitizeMetadata:
    def test_strips_prior_sql(self) -> None:
        meta = {"engine": "PostgreSQL", "prior_successful_sql": "SELECT 1"}
        out = sanitize_source_metadata_for_client(meta)
        assert out is not None
        assert "prior_successful_sql" not in out
        assert out["engine"] == "PostgreSQL"

    def test_none_passthrough(self) -> None:
        assert sanitize_source_metadata_for_client(None) is None
