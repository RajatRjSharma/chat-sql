"""Warehouse connect helper: timeouts, SSRF, and TLS policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.warehouse.connect import connect_warehouse


def test_connect_warehouse_passes_timeouts_and_ssrf() -> None:
    mock_conn = MagicMock()
    with patch("app.warehouse.connect.assert_safe_warehouse_host") as mock_ssrf:
        with patch(
            "app.warehouse.connect.psycopg2.connect", return_value=mock_conn
        ) as mock_connect:
            with patch("app.warehouse.connect.settings") as mock_settings:
                mock_settings.warehouse_connect_timeout_seconds = 7
                mock_settings.warehouse_statement_timeout_ms = 12_000
                mock_settings.is_local = True
                result = connect_warehouse(
                    "postgresql://u:p@localhost:5433/db",
                    host="localhost",
                )

    assert result is mock_conn
    mock_ssrf.assert_called_once_with("localhost")
    kwargs = mock_connect.call_args.kwargs
    assert kwargs["connect_timeout"] == 7
    assert "statement_timeout=12000" in kwargs["options"]
    assert kwargs["application_name"] == "meridian"


def test_connect_warehouse_omits_ssl_locally() -> None:
    """Local Docker Postgres has no TLS; forcing sslmode would break the demo."""
    with patch("app.warehouse.connect.assert_safe_warehouse_host"):
        with patch("app.warehouse.connect.psycopg2.connect") as mock_connect:
            with patch("app.warehouse.connect.settings") as mock_settings:
                mock_settings.warehouse_connect_timeout_seconds = 10
                mock_settings.warehouse_statement_timeout_ms = 15_000
                mock_settings.is_local = True
                connect_warehouse("postgresql://u:p@localhost:5432/db")

    assert "sslmode" not in mock_connect.call_args.kwargs


def test_connect_warehouse_requires_ssl_when_not_local() -> None:
    """Render/Supabase reject plaintext connections."""
    with patch("app.warehouse.connect.assert_safe_warehouse_host"):
        with patch("app.warehouse.connect.psycopg2.connect") as mock_connect:
            with patch("app.warehouse.connect.settings") as mock_settings:
                mock_settings.warehouse_connect_timeout_seconds = 10
                mock_settings.warehouse_statement_timeout_ms = 15_000
                mock_settings.is_local = False
                connect_warehouse("postgresql://u:p@db.example.com:5432/db")

    assert mock_connect.call_args.kwargs["sslmode"] == "require"


def test_connect_warehouse_derives_host_from_dsn() -> None:
    with patch("app.warehouse.connect.assert_safe_warehouse_host") as mock_ssrf:
        with patch("app.warehouse.connect.psycopg2.connect"):
            with patch("app.warehouse.connect.settings") as mock_settings:
                mock_settings.warehouse_connect_timeout_seconds = 10
                mock_settings.warehouse_statement_timeout_ms = 15_000
                mock_settings.is_local = False
                connect_warehouse("postgresql://u:p@db.example.com:5432/db")

    mock_ssrf.assert_called_once_with("db.example.com")


def test_connect_warehouse_merges_caller_options() -> None:
    with patch("app.warehouse.connect.assert_safe_warehouse_host"):
        with patch("app.warehouse.connect.psycopg2.connect") as mock_connect:
            with patch("app.warehouse.connect.settings") as mock_settings:
                mock_settings.warehouse_connect_timeout_seconds = 10
                mock_settings.warehouse_statement_timeout_ms = 9_000
                mock_settings.is_local = True
                connect_warehouse(
                    "postgresql://u:p@localhost:5432/db",
                    options="-c search_path=sales",
                )

    options = mock_connect.call_args.kwargs["options"]
    assert "search_path=sales" in options
    assert "statement_timeout=9000" in options
