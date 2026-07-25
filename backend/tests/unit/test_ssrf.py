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

    def test_allows_app_db_host_without_dns(self) -> None:
        """Uploads land in the project DB, so its host is trusted without resolving."""
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "dpg-example.singapore-postgres.render.com"
            mock_settings.allow_private_warehouse_hosts = False
            assert_safe_warehouse_host("dpg-example.singapore-postgres.render.com")

    def test_app_db_host_trust_is_case_and_dot_insensitive(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "Dpg-Example.Render.com"
            mock_settings.allow_private_warehouse_hosts = False
            assert_safe_warehouse_host("dpg-example.render.com.")

    def test_app_db_host_trust_allows_private_app_db(self) -> None:
        """A private APP_DB_HOST (docker/VPC) must not be rejected by the public policy."""
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "10.0.0.5"
            mock_settings.allow_private_warehouse_hosts = False
            assert_safe_warehouse_host("10.0.0.5")

    def test_app_db_host_trust_never_allows_metadata_ip(self) -> None:
        """Even a misconfigured APP_DB_HOST cannot open a path to cloud metadata."""
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "169.254.169.254"
            mock_settings.allow_private_warehouse_hosts = True
            with pytest.raises(ValueError, match="not allowed"):
                assert_safe_warehouse_host("169.254.169.254")

    def test_app_db_host_trust_does_not_leak_to_other_hosts(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "dpg-example.render.com"
            mock_settings.allow_private_warehouse_hosts = False
            with patch(
                "app.security.ssrf._resolve_ips",
                return_value=[ipaddress.ip_address("10.0.0.5")],
            ):
                with pytest.raises(ValueError, match="Private or loopback"):
                    assert_safe_warehouse_host("evil.example")

    def test_allows_public_ipv4_hostname(self) -> None:
        """Regression: IPv4Address has no is_site_local on Python 3.14+."""
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "localhost"
            mock_settings.allow_private_warehouse_hosts = False
            with patch(
                "app.security.ssrf._resolve_ips",
                return_value=[ipaddress.ip_address("104.18.32.7")],
            ):
                assert_safe_warehouse_host("aws-0-ap-southeast-1.pooler.supabase.com")

    def test_private_helper_handles_ipv4_without_site_local(self) -> None:
        from app.security.ssrf import _is_private_or_loopback

        public = ipaddress.ip_address("8.8.8.8")
        private = ipaddress.ip_address("10.1.2.3")
        assert _is_private_or_loopback(public) is False
        assert _is_private_or_loopback(private) is True

    def test_private_helper_still_flags_ipv6_site_local(self) -> None:
        """is_site_local is IPv6-only; the getattr fallback must not lose it."""
        from app.security.ssrf import _is_private_or_loopback

        assert _is_private_or_loopback(ipaddress.ip_address("fec0::1")) is True
        assert _is_private_or_loopback(ipaddress.ip_address("::1")) is True

    def test_blocks_private_ipv6_dns_when_denied(self) -> None:
        with patch("app.security.ssrf.settings") as mock_settings:
            mock_settings.app_db_host = "localhost"
            mock_settings.allow_private_warehouse_hosts = False
            with patch(
                "app.security.ssrf._resolve_ips",
                return_value=[ipaddress.ip_address("fec0::1")],
            ):
                with pytest.raises(ValueError, match="Private or loopback"):
                    assert_safe_warehouse_host("internal6.corp.example")
