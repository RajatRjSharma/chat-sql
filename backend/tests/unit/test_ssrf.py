"""SSRF / warehouse host policy tests."""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import pytest

from app.security.ssrf import assert_safe_warehouse_host


class TestAssertSafeWarehouseHost:
    def test_allows_localhost_when_private_allowed(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.allow_private_warehouse_hosts = True
            assert_safe_warehouse_host("localhost")
            assert_safe_warehouse_host("127.0.0.1")

    def test_blocks_localhost_when_private_denied(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.allow_private_warehouse_hosts = False
            with pytest.raises(ValueError, match="Private or loopback"):
                assert_safe_warehouse_host("127.0.0.1")

    def test_blocks_metadata_ip_always(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.allow_private_warehouse_hosts = True
            with pytest.raises(ValueError, match="not allowed"):
                assert_safe_warehouse_host("169.254.169.254")

    def test_blocks_metadata_hostname(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.allow_private_warehouse_hosts = True
            with pytest.raises(ValueError, match="not allowed"):
                assert_safe_warehouse_host("metadata.google.internal")

    def test_rejects_url_shaped_host(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.allow_private_warehouse_hosts = True
            with pytest.raises(ValueError, match="not a URL"):
                assert_safe_warehouse_host("postgresql://evil.example")

    def test_blocks_private_dns_when_denied(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.allow_private_warehouse_hosts = False
            with patch(
                "app.security.ssrf._resolve_ips",
                return_value=[ipaddress.ip_address("10.0.0.5")],
            ):
                with pytest.raises(ValueError, match="Private or loopback"):
                    assert_safe_warehouse_host("internal.corp.example")
