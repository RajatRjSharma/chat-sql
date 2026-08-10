"""Unit tests for IntentRouter + EntityLinker (LLM mocked / fallback path)."""

from __future__ import annotations

import pytest

from app.core.exceptions import AIProviderError
from app.services.entity_linker import EntityLinker
from app.services.intent_router import IntentRouter


class _FakeAI:
    def __init__(self, text: str | None = None, *, error: bool = False) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict] = []

    def complete(self, messages, **kwargs):  # noqa: ANN001
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self.error:
            raise AIProviderError("boom")
        return self.text or ""


class TestIntentRouter:
    def test_normalize_dp_typo_in_overview_context(self) -> None:
        assert IntentRouter.normalize_question("summary for the DP") == "summary for the db"

    def test_normalize_dp_department_unchanged(self) -> None:
        assert IntentRouter.normalize_question("list employees in DP") == "list employees in DP"

    def test_fallback_catalog_dp(self) -> None:
        d = IntentRouter.fallback("tell me the summary for the DP")
        assert d.intent == "catalog_overview"
        assert "db" in d.normalized_question.lower()

    def test_fallback_catalog_db(self) -> None:
        d = IntentRouter.fallback("give me SUMMARY FOR THE DB")
        assert d.intent == "catalog_overview"

    def test_fallback_clarify_bare_summary(self) -> None:
        d = IntentRouter.fallback("summary")
        assert d.intent == "clarify"

    def test_fallback_out_of_scope_world_cup(self) -> None:
        d = IntentRouter.fallback("WHO WON WORLD CUP")
        assert d.intent == "out_of_scope"

    def test_fallback_analytics_revenue(self) -> None:
        d = IntentRouter.fallback(
            "give me revenue BASED ON REGION AND SALES CHANNEL",
            table_names=["orders", "regions", "channels", "customers"],
        )
        assert d.intent == "analytics"

    def test_fallback_follow_up_with_prior(self) -> None:
        history = [
            {"role": "user", "content": "revenue by region and channel"},
            {"role": "assistant", "content": "Here is revenue by region…"},
        ]
        d = IntentRouter.fallback(
            "BREAK DOWN THE MONTHLY REVENUE FOR THE NORTH",
            history=history,
            prior_sql_present=True,
            table_names=["orders", "regions", "channels"],
        )
        assert d.intent == "follow_up"

    def test_parse_decision_json(self) -> None:
        raw = (
            '{"intent":"catalog_overview","confidence":0.9,'
            '"reason":"db summary","normalized_question":"summary for the database"}'
        )
        d = IntentRouter.parse_decision(raw, question="summary for the DP")
        assert d is not None
        assert d.intent == "catalog_overview"
        assert d.confidence == pytest.approx(0.9)

    def test_route_uses_llm_then_safety(self) -> None:
        ai = _FakeAI(
            '{"intent":"out_of_scope","confidence":0.9,"reason":"x",'
            '"normalized_question":"summary for the db"}'
        )
        d = IntentRouter.route(
            "summary for the db",
            table_names=["orders"],
            client=ai,  # type: ignore[arg-type]
        )
        # Safety net flips false out_of_scope catalog asks → catalog_overview
        assert d.intent == "catalog_overview"
        assert ai.calls
        assert ai.calls[0]["kwargs"].get("preferred_model")

    def test_route_fallback_on_llm_error(self) -> None:
        ai = _FakeAI(error=True)
        d = IntentRouter.route(
            "give me SUMMARY FOR THE DB",
            client=ai,  # type: ignore[arg-type]
        )
        assert d.intent == "catalog_overview"
        assert d.source == "fallback"


class TestEntityLinker:
    def test_fallback_revenue_region_channel(self) -> None:
        from app.services.schema_linker import SchemaChunk

        catalog = [
            SchemaChunk(
                table="orders",
                content=(
                    "Table: sales.orders\nColumns:\n"
                    "  - order_id: integer (PK)\n"
                    "  - amount: numeric\n"
                    "  - order_date: date\n"
                    "  - channel_id: integer"
                ),
                metadata={"foreign_keys": []},
            ),
            SchemaChunk(
                table="customers",
                content=(
                    "Table: sales.customers\nColumns:\n"
                    "  - customer_id: integer (PK)\n"
                    "  - region: varchar"
                ),
                metadata={"foreign_keys": []},
            ),
            SchemaChunk(
                table="channels",
                content=(
                    "Table: sales.channels\nColumns:\n"
                    "  - channel_id: integer (PK)\n"
                    "  - name: varchar"
                ),
                metadata={"foreign_keys": []},
            ),
        ]
        result = EntityLinker.fallback(
            "revenue by region and channel",
            table_names=["orders", "customers", "channels"],
            catalog_chunks=catalog,
        )
        assert "revenue" in result.measures
        assert "region" in result.dimensions
        assert "channel" in result.dimensions

    def test_fallback_filter_from_phrase_not_wordlist(self) -> None:
        result = EntityLinker.fallback(
            "Total leave days for Engineering",
            table_names=["leave_requests", "employees"],
        )
        assert "Engineering" in result.filters
        assert "Web Store" not in result.filters

    def test_parse_and_resolve_tables(self) -> None:
        raw = (
            '{"tables":["orders","regions"],"measures":["revenue"],'
            '"dimensions":["region","channel"],"filters":["North"],'
            '"time_grain":"month"}'
        )
        result = EntityLinker.parse(
            raw,
            table_names=["orders", "customers", "regions", "channels"],
        )
        assert result is not None
        assert "orders" in result.tables
        assert "regions" in result.tables
        assert result.time_grain == "month"
        assert "North" in result.filters

    def test_link_merges_llm_and_fallback(self) -> None:
        from app.services.schema_linker import SchemaChunk

        catalog = [
            SchemaChunk(
                table="orders",
                content=(
                    "Table: sales.orders\nColumns:\n"
                    "  - amount: numeric\n"
                    "  - order_date: date"
                ),
                metadata={},
            ),
            SchemaChunk(
                table="customers",
                content="Table: sales.customers\nColumns:\n  - region: varchar",
                metadata={},
            ),
            SchemaChunk(
                table="channels",
                content="Table: sales.channels\nColumns:\n  - name: varchar",
                metadata={},
            ),
        ]
        ai = _FakeAI(
            '{"tables":["orders"],"measures":["revenue"],'
            '"dimensions":["region"],"filters":[],"time_grain":null}'
        )
        result = EntityLinker.link(
            "revenue by region and channel",
            table_names=["orders", "regions", "channels", "customers"],
            catalog_chunks=catalog,
            client=ai,  # type: ignore[arg-type]
        )
        assert result.source == "llm"
        assert "orders" in result.tables
        assert "revenue" in result.measures
        assert "channel" in result.dimensions  # from fallback merge
