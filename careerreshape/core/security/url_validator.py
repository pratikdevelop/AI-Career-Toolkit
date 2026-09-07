"""SSRF protection for user-supplied URLs.

Before any network request is made, the URL's scheme is restricted and
every IP address the hostname resolves to is checked against private,
loopback, link-local, and cloud-metadata ranges. This runs at resolution
time (right before connecting), not just against the literal hostname
string, to catch "friendly" hostnames that resolve to internal addresses.

This is a solid baseline, not a perfect one: a fully hardened setup would
also pin the validated IP through to the actual TCP connection (closing
the DNS-rebinding gap between validation and connection), which needs a
custom transport/adapter. Flagged here as a follow-up rather than
silently skipped.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from careerreshape.core.exceptions import UnsafeUrlError

_ALLOWED_SCHEMES = {"http", "https"}


def assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")

    try:
        resolved = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host: {parsed.hostname}") from exc

    for _family, _type, _proto, _canon, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeUrlError(
                f"Refusing to fetch {url!r}: resolves to a non-public address ({ip})"
            )
