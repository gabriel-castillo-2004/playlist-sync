"""External URL security validation against SSRF and oversized payloads (H-03)."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

from playlist_sync.core.errors import AppError, ErrorCode

MAX_XML_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_COVER_BYTES = 10 * 1024 * 1024  # 10 MB


def is_ip_global_and_safe(ip_str: str) -> bool:
    """Return True only if ip_str is a valid public/global IP address.

    Strictly rejects private, loopback, link-local, multicast, reserved,
    and unspecified addresses (including IPv4-mapped IPv6 addresses).
    """
    cleaned = ip_str.split("%")[0].strip()
    try:
        addr = ipaddress.ip_address(cleaned)
    except ValueError:
        return False

    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [addr]
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        candidates.append(addr.ipv4_mapped)

    for candidate in candidates:
        if (
            candidate.is_private
            or candidate.is_loopback
            or candidate.is_link_local
            or candidate.is_multicast
            or candidate.is_reserved
            or candidate.is_unspecified
            or not candidate.is_global
        ):
            return False

    return True


def resolve_hostname_ips(hostname: str) -> list[str]:
    """Resolve hostname via DNS and return all resolved IP strings."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AppError(
            ErrorCode.NETWORK,
            user_message="No hay conexión a internet o el servidor del podcast no responde.",
            technical_detail=f"DNS resolution failed for host {hostname!r}: {exc}",
        ) from exc

    ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and isinstance(sockaddr[0], str):
            ip_clean = sockaddr[0].split("%")[0]
            if ip_clean not in ips:
                ips.append(ip_clean)

    if not ips:
        raise AppError(
            ErrorCode.INVALID_URL,
            user_message="Ese link no parece de YouTube ni de un podcast válido.",
            technical_detail=f"No IP addresses resolved for host {hostname!r}",
        )
    return ips


def validate_external_url(
    url: str,
    resolver: Callable[[str], Sequence[str]] | None = None,
) -> str:
    """Validate an external URL against SSRF (scheme + literal IP + DNS resolution).

    1. Accepts only 'http' and 'https' schemes.
    2. Rejects localhost / .local hostnames.
    3. Rejects private, loopback, link-local, multicast, reserved, and unspecified IPs,
       both when given as literal IPs and after resolving the hostname via DNS.
    """
    cleaned_url = url.strip()
    parsed = urlparse(cleaned_url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise AppError(
            ErrorCode.INVALID_URL,
            user_message="Ese link no parece de YouTube ni de un podcast.",
            technical_detail=f"Disallowed URL scheme: {parsed.scheme!r}",
        )

    hostname = parsed.hostname
    if not hostname:
        raise AppError(
            ErrorCode.INVALID_URL,
            user_message="Ese link no parece de YouTube ni de un podcast válido.",
            technical_detail="Missing hostname in URL",
        )

    host_lower = hostname.lower().rstrip(".")
    if (
        host_lower == "localhost"
        or host_lower.endswith(".localhost")
        or host_lower.endswith(".local")
    ):
        raise AppError(
            ErrorCode.INVALID_URL,
            user_message="No se permiten direcciones locales o internas.",
            technical_detail=f"Blocked local hostname: {hostname!r}",
        )

    # Check if hostname is a literal IPv4/IPv6 address
    ip_candidate = host_lower.split("%")[0]
    try:
        ipaddress.ip_address(ip_candidate)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if not is_ip_global_and_safe(ip_candidate):
            raise AppError(
                ErrorCode.INVALID_URL,
                user_message="No se permiten direcciones privadas, locales o reservadas.",
                technical_detail=f"Blocked non-global literal IP: {hostname!r}",
            )
        return cleaned_url

    # Resolve domain name via DNS and verify every resolved IP is public/global
    resolved_ips = (
        list(resolver(host_lower)) if resolver is not None else resolve_hostname_ips(host_lower)
    )
    if not resolved_ips:
        raise AppError(
            ErrorCode.INVALID_URL,
            user_message="Ese link no parece de YouTube ni de un podcast válido.",
            technical_detail=f"Empty DNS resolution for {hostname!r}",
        )

    for ip_str in resolved_ips:
        if not is_ip_global_and_safe(ip_str):
            raise AppError(
                ErrorCode.INVALID_URL,
                user_message="No se permiten direcciones privadas, locales o reservadas.",
                technical_detail=f"Host {hostname!r} resolved to disallowed IP {ip_str!r}",
            )

    return cleaned_url
