"""SSRF guards for user-supplied warehouse hosts (enterprise outbound policy)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings

# Cloud / link-local metadata endpoints — always blocked, even in local mode.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "metadata.azure.com",
        "instance-data",
    }
)

_LOOPBACK_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def _is_hard_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Addresses that must never be dialed (metadata / link-local / multicast)."""
    if ip.is_unspecified or ip.is_multicast:
        return True
    if ip.is_link_local:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip == ipaddress.IPv4Address("169.254.169.254"):
        return True
    return False


def _is_private_or_loopback(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip.is_private or ip.is_loopback or ip.is_site_local)


def _is_loopback_hostname(host: str) -> bool:
    return host in _LOOPBACK_HOSTNAMES or host.endswith(".localhost")


def _resolve_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Warehouse host could not be resolved: {host}") from exc

    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        raw = info[4][0]
        if raw in seen:
            continue
        seen.add(raw)
        ips.append(ipaddress.ip_address(raw))
    if not ips:
        raise ValueError(f"Warehouse host could not be resolved: {host}")
    return ips


def _assert_ip_allowed(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private: bool,
) -> None:
    if _is_hard_blocked_ip(ip):
        raise ValueError("Warehouse host is not allowed.")
    if _is_private_or_loopback(ip) and not allow_private:
        raise ValueError(
            "Private or loopback warehouse hosts are disabled. "
            "Set WAREHOUSE_ALLOW_PRIVATE_HOSTS=true for local demos."
        )


def assert_safe_warehouse_host(host: str) -> None:
    """
    Reject hosts that would let the server reach internal/metadata networks.

    Local/dev may allow private/loopback IPs (demo Docker warehouse). Production
    defaults to public hosts only unless WAREHOUSE_ALLOW_PRIVATE_HOSTS=true.
    Metadata / link-local targets are always denied.
    """
    cleaned = (host or "").strip().lower().rstrip(".")
    if not cleaned:
        raise ValueError("Warehouse host is required.")
    if "://" in cleaned:
        raise ValueError("Warehouse host must be a hostname or IP, not a URL.")
    if cleaned in _BLOCKED_HOSTNAMES or cleaned.endswith(".metadata.google.internal"):
        raise ValueError("Warehouse host is not allowed.")

    allow_private = settings.allow_private_warehouse_hosts

    # Literal IP in the host field
    try:
        literal = ipaddress.ip_address(cleaned)
    except ValueError:
        literal = None

    if literal is not None:
        _assert_ip_allowed(literal, allow_private=allow_private)
        return

    if any(ch in cleaned for ch in ("/", "?", "#", "@", " ")):
        raise ValueError("Warehouse host contains invalid characters.")

    # Treat localhost as loopback without DNS (stable for demos + tests).
    if _is_loopback_hostname(cleaned):
        if not allow_private:
            raise ValueError(
                "Private or loopback warehouse hosts are disabled. "
                "Set WAREHOUSE_ALLOW_PRIVATE_HOSTS=true for local demos."
            )
        return

    for ip in _resolve_ips(cleaned):
        _assert_ip_allowed(ip, allow_private=allow_private)


def host_from_postgres_url(url: str) -> str | None:
    """Best-effort host extraction from a postgresql:// URL."""
    try:
        return urlparse(url).hostname
    except Exception:
        return None
