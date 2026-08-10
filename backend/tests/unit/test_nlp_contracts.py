"""Tests for shared NLP JSON contracts and LLM-first routing trust."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.intent_router import IntentRouter
from app.services.nlp_json import clamp_confidence, extract_json_object
from app.services.scope_guard import ScopeGuard


class TestNlpJson:
    def test_extract_fenced_json(self) -> None:
        raw = 'Here\n```json\n{"intent":"analytics","confidence":0.8}\n```\n'
        data = extract_json_object(raw)
        assert data is not None
        assert data["intent"] == "analytics"

    def test_extract_bare_json(self) -> None:
        data = extract_json_object('{"decision":"OUT_OF_SCOPE","confidence":0.9}')
        assert data is not None
        assert data["decision"] == "OUT_OF_SCOPE"

    def test_clamp_confidence(self) -> None:
        assert clamp_confidence("1.5") == 1.0
        assert clamp_confidence("-1") == 0.0
        assert clamp_confidence("nope", default=0.4) == 0.4


class TestScopeJsonContract:
    def test_parse_json_decision(self) -> None:
        assert (
            ScopeGuard.parse_decision(
                '{"decision":"NEEDS_CLARIFICATION","confidence":0.7}'
            )
            == "needs_clarification"
        )

    def test_parse_legacy_token_still_works(self) -> None:
        assert ScopeGuard.parse_decision("OUT_OF_SCOPE") == "out_of_scope"

    def test_trusts_pre_decision_above_threshold(self) -> None:
        mock = MagicMock()
        decision = ScopeGuard.assess(
            question="who won world cup",
            schema_context="Table: orders",
            allowed_tables=["orders"],
            pre_decision="out_of_scope",
            intent_confidence=0.9,
            client=mock,
        )
        mock.complete.assert_not_called()
        assert decision == "out_of_scope"


class TestLlmFirstRouting:
    def test_route_skips_llm_when_prefer_false(self) -> None:
        ai = MagicMock()
        with patch("app.services.intent_router.settings") as mock_settings:
            mock_settings.nlp_prefer_llm = False
            mock_settings.effective_llm_router_model = "x"
            mock_settings.nlp_router_max_tokens = 120
            mock_settings.nlp_intent_confidence_trust = 0.55
            d = IntentRouter.route(
                "give me SUMMARY FOR THE DB",
                client=ai,
            )
        ai.complete.assert_not_called()
        assert d.intent == "catalog_overview"
        assert d.source == "fallback"

    def test_llm_intent_trusted_property(self) -> None:
        d = IntentRouter.parse_decision(
            '{"intent":"analytics","confidence":0.8,"reason":"ok",'
            '"normalized_question":"revenue by region"}',
            question="revenue by region",
        )
        assert d is not None
        assert d.source == "llm"
        assert d.trusted is True
