"""Stateless JWT access + refresh tokens (no server-side session store)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from jose import JWTError, jwt

from app.config import settings

TokenType = Literal["access", "refresh"]


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(
    *,
    user_id: UUID,
    email: str,
    username: str,
    role: str,
) -> tuple[str, int]:
    """Return (token, expires_in_seconds). Short-lived; pair with refresh."""
    expires_in = settings.jwt_expire_minutes * 60
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "username": username,
        "role": role,
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": secrets.token_urlsafe(16),
        "iss": settings.jwt_issuer,
        "type": "access",
    }
    return _encode(payload), expires_in


def create_refresh_token(*, user_id: UUID) -> tuple[str, int]:
    """Longer-lived refresh JWT — still stateless (no DB session)."""
    expires_in = settings.jwt_refresh_expire_minutes * 60
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": secrets.token_urlsafe(16),
        "iss": settings.jwt_issuer,
        "type": "refresh",
    }
    return _encode(payload), expires_in


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("type") != expected_type or not payload.get("sub"):
        raise ValueError("Invalid token claims")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, expected_type="access")
