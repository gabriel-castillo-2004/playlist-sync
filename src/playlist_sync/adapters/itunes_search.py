"""Adapter for searching public podcasts via the Apple iTunes Search API (RF-13)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from playlist_sync.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


@dataclass(frozen=True)
class PodcastSearchResult:
    """A podcast returned by the iTunes Search API."""

    title: str
    artist: str
    feed_url: str
    cover_url: str | None = None
    track_count: int | None = None
    genre: str | None = None


def search_itunes_podcasts(
    query: str,
    limit: int = 10,
    client: httpx.Client | None = None,
    timeout: float = 10.0,
) -> list[PodcastSearchResult]:
    """Search for podcasts by title or topic using iTunes public search API.

    No API key required.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    params = {
        "term": clean_query,
        "media": "podcast",
        "entity": "podcast",
        "limit": min(max(limit, 1), 50),
    }

    url = f"{ITUNES_SEARCH_URL}?{urlencode(params)}"
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)

    try:
        resp = http.get(url)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("Network error while searching iTunes for '%s': %s", clean_query, exc)
        raise AppError(
            ErrorCode.NETWORK,
            user_message="No se pudo buscar podcasts. Revisa tu conexión a internet.",
            technical_detail=f"iTunes search network error: {exc}",
        ) from exc
    except Exception as exc:
        logger.warning("Unexpected error during iTunes search for '%s': %s", clean_query, exc)
        raise AppError(
            ErrorCode.UNKNOWN,
            technical_detail=f"iTunes search failed: {exc}",
        ) from exc
    finally:
        if owns_client:
            http.close()

    results: list[PodcastSearchResult] = []
    for item in data.get("results", []):
        feed_url = item.get("feedUrl")
        collection_name = item.get("collectionName")
        if not feed_url or not collection_name:
            continue

        results.append(
            PodcastSearchResult(
                title=str(collection_name).strip(),
                artist=str(item.get("artistName", "")).strip(),
                feed_url=str(feed_url).strip(),
                cover_url=item.get("artworkUrl600") or item.get("artworkUrl100"),
                track_count=item.get("trackCount"),
                genre=item.get("primaryGenreName"),
            )
        )

    return results
