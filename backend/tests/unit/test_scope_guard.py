"""Unit tests for warehouse scope guard."""

from __future__ import annotations

from app.services.scope_guard import ScopeGuard


class TestScopeGuardParse:
    def test_answerable(self) -> None:
        assert ScopeGuard.parse_decision("ANSWERABLE") == "answerable"

    def test_out_of_scope(self) -> None:
        assert ScopeGuard.parse_decision("OUT_OF_SCOPE") == "out_of_scope"

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
