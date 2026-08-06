"""Client-safe error detail helpers."""

from __future__ import annotations

from app.security.http_errors import GENERIC_AI, GENERIC_CHAT, GENERIC_CONNECT, safe_public_detail


class TestSafePublicDetail:
    def test_passes_short_domain_message(self) -> None:
        assert safe_public_detail(ValueError("invalid credentials"), fallback="x") == (
            "invalid credentials"
        )

    def test_strips_driver_leaks(self) -> None:
        assert (
            safe_public_detail(
                RuntimeError("psycopg2.OperationalError: connection refused"),
                fallback=GENERIC_CONNECT,
            )
            == GENERIC_CONNECT
        )

    def test_strips_long_messages(self) -> None:
        long = "x" * 400
        assert safe_public_detail(Exception(long), fallback="safe") == "safe"

    def test_strips_index_error(self) -> None:
        assert (
            safe_public_detail(IndexError("list index out of range"), fallback=GENERIC_AI)
            == GENERIC_AI
        )

    def test_strips_index_error_message_string(self) -> None:
        assert (
            safe_public_detail(Exception("list index out of range"), fallback=GENERIC_CHAT)
            == GENERIC_CHAT
        )
