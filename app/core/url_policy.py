"""SSRF-safe URL ingestion policy boundary.

This module deliberately performs **no network access**. It only evaluates
whether a URL would be allowed to be fetched under current configuration so
that callers can persist a deterministic decision without ever making a
request.

The product decision for the actual allow/deny list (which external hosts, if
any, may ever be fetched) is intentionally left unresolved: when no allowlist
is configured the policy denies all URLs. This is the configuration seam that
a future durable fetcher must honour.
"""

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.config import Settings, get_settings

ALLOWED_SCHEME_DEFAULTS: frozenset[str] = frozenset({"http", "https"})
BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
)


class UrlPolicyError(ValueError):
    """Raised when a URL is structurally invalid for ingestion."""


@dataclass(frozen=True)
class UrlDecision:
    """Immutable result of evaluating a URL against ingestion policy."""

    allowed: bool
    reason: str
    host: str | None = None


def _parse_allowed_schemes(settings: Settings) -> frozenset[str]:
    raw = (settings.URL_ALLOWED_SCHEMES or "").strip()
    if not raw:
        return ALLOWED_SCHEME_DEFAULTS
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def _parse_allowed_hosts(settings: Settings) -> frozenset[str]:
    raw = (settings.URL_ALLOWED_HOSTS or "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def parse_url(url: str) -> tuple[str, str]:
    """Return ``(scheme, host)`` for a structurally valid URL.

    Raises :class:`UrlPolicyError` when the URL is not an absolute URL with a
    host component.
    """

    candidate = (url or "").strip()
    if not candidate:
        raise UrlPolicyError("URL must not be empty")
    parts = urlsplit(candidate)
    if not parts.scheme or not parts.netloc:
        raise UrlPolicyError("URL must be absolute and include a host")
    if parts.username or parts.password:
        raise UrlPolicyError("URL must not contain embedded credentials")
    host = parts.hostname
    if not host:
        raise UrlPolicyError("URL must include a host")
    return parts.scheme.lower(), host.lower()


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _ip_is_forbidden(host: str) -> bool:
    address = ipaddress.ip_address(host)
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _host_matches_allowlist(host: str, allowlist: frozenset[str]) -> bool:
    return any(
        host == entry or host.endswith(f".{entry}") for entry in allowlist
    )


def evaluate_url(url: str, settings: Settings | None = None) -> UrlDecision:
    """Evaluate a URL against the URL-ingestion policy without fetching it."""

    active = settings or get_settings()

    scheme, host = parse_url(url)

    if scheme not in _parse_allowed_schemes(active):
        return UrlDecision(False, f"scheme '{scheme}' is not allowed", host)

    if host in BLOCKED_HOSTNAMES:
        return UrlDecision(False, "host is a reserved localhost name", host)

    if _is_ip_literal(host) and _ip_is_forbidden(host):
        return UrlDecision(False, "host resolves to a non-public IP address", host)

    if not active.URL_INGESTION_ENABLED:
        return UrlDecision(False, "URL ingestion is disabled by policy", host)

    allowlist = _parse_allowed_hosts(active)
    if not allowlist:
        return UrlDecision(
            False,
            "URL allowlist is not configured; external fetching is unresolved",
            host,
        )

    if not _host_matches_allowlist(host, allowlist):
        return UrlDecision(False, "host is not in the configured allowlist", host)

    return UrlDecision(True, "host is permitted by policy", host)
