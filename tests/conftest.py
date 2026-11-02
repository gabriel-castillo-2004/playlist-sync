"""Pytest configuration and isolated offline RFC 2606 DNS stub for sandboxed unit tests."""

from __future__ import annotations

import pytest

from playlist_sync.core import url_security

_REAL_RESOLVE_HOSTNAME_IPS = url_security.resolve_hostname_ips


@pytest.fixture(autouse=True)
def _offline_rfc2606_dns_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve RFC 2606 documentation domains (example.com/org/net) to public IP 93.184.216.34 when offline."""

    def _resolve_with_rfc2606_fallback(hostname: str) -> list[str]:
        host_lower = hostname.lower().rstrip(".")
        if any(
            host_lower == domain or host_lower.endswith("." + domain)
            for domain in ("example.com", "example.org", "example.net")
        ):
            return ["93.184.216.34"]
        if host_lower == "fake.url":
            from playlist_sync.core.errors import AppError, ErrorCode

            raise AppError(
                ErrorCode.NETWORK,
                technical_detail="Offline mock host fake.url",
            )
        return _REAL_RESOLVE_HOSTNAME_IPS(hostname)

    monkeypatch.setattr(url_security, "resolve_hostname_ips", _resolve_with_rfc2606_fallback)
