"""Auth cookie attribute helpers."""

from __future__ import annotations

from unittest.mock import patch

from app.security import auth_cookies


class TestAuthCookieSecure:
    def test_samesite_none_forces_secure(self) -> None:
        with patch.object(auth_cookies.settings, "auth_cookie_samesite", "none"):
            with patch.object(auth_cookies.settings, "auth_cookie_secure", False):
                assert auth_cookies._secure() is True

    def test_lax_follows_explicit_secure_flag(self) -> None:
        with patch.object(auth_cookies.settings, "auth_cookie_samesite", "lax"):
            with patch.object(auth_cookies.settings, "auth_cookie_secure", True):
                assert auth_cookies._secure() is True
            with patch.object(auth_cookies.settings, "auth_cookie_secure", False):
                assert auth_cookies._secure() is False
