"""Safe client-facing HTTP error details (no internal/driver leaks)."""

from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

GENERIC_BAD_GATEWAY = "Upstream service failed. Please try again."
GENERIC_INTERNAL = "Something went wrong. Please try again."
GENERIC_CONNECT = "Could not connect to the warehouse. Check host, port, and credentials."
GENERIC_UPLOAD = "Upload failed. Check the file and try again."
GENERIC_EMBED = "Schema embedding failed. Please try again."
GENERIC_CHAT = "Chat failed. Please try again."
GENERIC_AI = "AI provider is temporarily unavailable. Please try again shortly."
GENERIC_EMAIL = "Could not send email. Please try again later."


def raise_http(
    status_code: int,
    *,
    detail: str,
    exc: BaseException | None = None,
) -> NoReturn:
    """Raise HTTPException; log unexpected causes server-side only."""
    if exc is not None and status_code >= 500:
        logger.exception("HTTP %s: %s", status_code, detail, exc_info=exc)
    elif exc is not None and status_code >= 400:
        logger.warning("HTTP %s: %s (%s)", status_code, detail, exc)
    raise HTTPException(status_code=status_code, detail=detail)


def safe_public_detail(exc: BaseException, *, fallback: str) -> str:
    """
    Prefer intentional domain messages; hide raw driver/provider stacks.

    ValueError and our AppError subclasses with short, crafted messages are OK.
    Long / low-level strings are replaced with fallback.
    """
    text = str(exc).strip()
    if not text:
        return fallback
    lowered = text.lower()
    leak_markers = (
        "traceback",
        "psycopg2",
        "sqlalchemy",
        "operationalerror",
        "connection refused",
        "password authentication failed",
        "api key",
        "authorization",
        "sk-or-",
        "openrouter",
        "ssl",
        "errno",
        "file \"",
        "  file ",
    )
    if any(marker in lowered for marker in leak_markers):
        return fallback
    if len(text) > 280:
        return fallback
    return text
