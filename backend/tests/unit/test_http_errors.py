"""Client-safe error detail helpers."""

from __future__ import annotations

from app.security.http_errors import GENERIC_CONNECT, safe_public_detail


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
