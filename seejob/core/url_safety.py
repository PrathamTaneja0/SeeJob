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
        "www.github.com",
        "api.github.com",
    }
)

JOB_BOARD_HOST_SUFFIXES = (
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "workday.com",
    "linkedin.com",
    "indeed.com",
    "icims.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "jobvite.com",
    "bamboohr.com",
    "recruitee.com",
    "workable.com",
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


def _normalize_host(host: str) -> str:
    return host.lower().rstrip(".")


def _validate_https_host(hostname: str) -> str:
    host = _normalize_host(hostname)
    if not host:
        raise URLValidationError("URL must include a hostname")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            resolved_ips = _resolve_host_ips(host)
        except URLValidationError:
            resolved_ips = []
        for ip in resolved_ips:
            if _is_blocked_ip(ip):
                raise URLValidationError(f"Host resolves to blocked address: {ip}")
    else:
        if _is_blocked_ip(host):
            raise URLValidationError(f"Blocked IP address: {host}")

    return host


def _host_matches_job_allowlist(host: str) -> bool:
    if host.startswith("jobs."):
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in JOB_BOARD_HOST_SUFFIXES)


def validate_job_url(url: str) -> None:
    """Validate URL for job sourcing (job-board allowlist, no private IPs)."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise URLValidationError(
            f"URL scheme {parsed.scheme!r} is not allowed; use HTTPS"
        )

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname")

    host = _validate_https_host(hostname)
    if not _host_matches_job_allowlist(host):
        raise URLValidationError(f"Host {host!r} is not an allowed job board")
