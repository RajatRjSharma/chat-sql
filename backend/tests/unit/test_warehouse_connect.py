"""Warehouse connect helper timeouts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.warehouse.connect import connect_warehouse


def test_connect_warehouse_passes_timeouts_and_ssrf() -> None:
    mock_conn = MagicMock()
    with patch("app.warehouse.connect.assert_safe_warehouse_host") as mock_ssrf:
        with patch("app.warehouse.connect.psycopg2.connect", return_value=mock_conn) as mock_connect:
            with patch("app.warehouse.connect.settings") as mock_settings:
                mock_settings.warehouse_connect_timeout_seconds = 7
                mock_settings.warehouse_statement_timeout_ms = 12_000
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
