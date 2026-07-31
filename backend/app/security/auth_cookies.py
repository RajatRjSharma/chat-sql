"""httpOnly auth cookie helpers (access + refresh).

Prefer first-party cookies via the Next.js /api rewrite (same site as the UI).
Cross-site cookies (Vercel page → Render API) fail on many mobile browsers even
with SameSite=None; use the proxy and SameSite=Lax in production.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Response

from app.config import settings

SameSite = Literal["lax", "strict", "none"]


def access_cookie_name() -> str:
    return settings.auth_access_cookie_name


def refresh_cookie_name() -> str:
    return settings.auth_refresh_cookie_name


def _samesite() -> SameSite:
    value = settings.auth_cookie_samesite.lower()
    if value not in {"lax", "strict", "none"}:
        return "lax"
    return value  # type: ignore[return-value]


def _secure() -> bool:
    # SameSite=None is rejected by browsers unless Secure is set.
    if _samesite() == "none":
        return True
    if settings.auth_cookie_secure is not None:
        return settings.auth_cookie_secure
    return not settings.is_local


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    access_max_age: int,
    refresh_max_age: int,
) -> None:
    """Attach access + refresh httpOnly cookies to the response."""
    common = {
        "httponly": True,
        "secure": _secure(),
        "samesite": _samesite(),
        "path": "/",
    }
    response.set_cookie(
        key=access_cookie_name(),
        value=access_token,
        max_age=access_max_age,
        **common,
    )
    response.set_cookie(
        key=refresh_cookie_name(),
        value=refresh_token,
        max_age=refresh_max_age,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    """Expire auth cookies (logout / failed refresh)."""
    common = {
        "httponly": True,
        "secure": _secure(),
        "samesite": _samesite(),
        "path": "/",
    }
    response.delete_cookie(key=access_cookie_name(), **common)
    response.delete_cookie(key=refresh_cookie_name(), **common)
