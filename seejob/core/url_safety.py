"""SSRF-safe URL validation for outbound profile link fetching."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from seejob.core.exceptions import URLValidationError

ALLOWED_FETCH_HOSTS = frozenset(
    {
        "linkedin.com",
        "www.linkedin.com",
        "github.com",
        "api.github.com",
    }
)

_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    return any(addr in network for network in _BLOCKED_NETWORKS)


def _resolve_host_ips(hostname: str) -> list[str]:
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise URLValidationError(f"Could not resolve host: {hostname}") from exc
    return [info[4][0] for info in results]


def validate_fetch_url(url: str) -> None:
    """Validate URL scheme, host allowlist, and resolved IPs for SSRF safety."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise URLValidationError("Only HTTPS URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL must include a hostname")

    host_lower = hostname.lower().rstrip(".")
    if host_lower not in ALLOWED_FETCH_HOSTS:
        raise URLValidationError(f"Host not allowed: {hostname}")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        for ip in _resolve_host_ips(hostname):
            if _is_blocked_ip(ip):
                raise URLValidationError(f"Host resolves to blocked address: {ip}")
    else:
        if _is_blocked_ip(hostname):
            raise URLValidationError(f"Blocked IP address: {hostname}")
