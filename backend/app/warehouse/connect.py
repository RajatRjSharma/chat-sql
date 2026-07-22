"""Shared psycopg2 connect with timeouts + SSRF host checks."""

from __future__ import annotations

from typing import Any

import psycopg2
from psycopg2.extensions import connection as PgConnection

from app.config import settings
from app.security.ssrf import assert_safe_warehouse_host, host_from_postgres_url


def connect_warehouse(
    dsn: str,
    *,
    host: str | None = None,
    statement_timeout_ms: int | None = None,
    **kwargs: Any,
) -> PgConnection:
    """
    Open a warehouse connection with connect + statement timeouts.

    Always validates the target host against SSRF policy.
    """
    resolved_host = host or host_from_postgres_url(dsn)
    if resolved_host:
        assert_safe_warehouse_host(resolved_host)

    timeout_ms = (
        settings.warehouse_statement_timeout_ms
        if statement_timeout_ms is None
        else statement_timeout_ms
    )
    options = kwargs.pop("options", None)
    timeout_opt = f"-c statement_timeout={max(0, int(timeout_ms))}"
    merged_options = f"{options} {timeout_opt}".strip() if options else timeout_opt

    return psycopg2.connect(
        dsn,
        connect_timeout=settings.warehouse_connect_timeout_seconds,
        options=merged_options,
        application_name="meridian",
        **kwargs,
    )
