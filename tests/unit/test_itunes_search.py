"""Unit tests for the iTunes Podcast Search Adapter (RF-13)."""

from __future__ import annotations

import httpx
import pytest

from playlist_sync.adapters.itunes_search import ITUNES_SEARCH_URL, search_itunes_podcasts
from playlist_sync.core.errors import AppError, ErrorCode


def test_empty_query_returns_empty_list() -> None:
    results = search_itunes_podcasts("   ")
    assert results == []


def test_successful_itunes_search() -> None:
    fake_payload = {
        "resultCount": 2,
        "results": [
            {
                "collectionName": "Radio Ambulante",
                "artistName": "NPR",
                "feedUrl": "https://feeds.npr.org/510315/podcast.xml",
                "artworkUrl600": "https://example.com/art600.jpg",
                "artworkUrl100": "https://example.com/art100.jpg",
                "trackCount": 150,
                "primaryGenreName": "News",
            },
            {
                "collectionName": "El Hilo",
                "artistName": "Radio Ambulante Estudios",
                "feedUrl": "https://feeds.elhilo.audio/podcast.xml",
                "artworkUrl100": "https://example.com/elhilo.jpg",
                "trackCount": 80,
                "primaryGenreName": "Society & Culture",
            },
        ],
    }

    def custom_transport(request: httpx.Request) -> httpx.Response:
        assert ITUNES_SEARCH_URL in str(request.url)
        assert "media=podcast" in str(request.url)
        return httpx.Response(200, json=fake_payload)

    client = httpx.Client(transport=httpx.MockTransport(custom_transport))
    results = search_itunes_podcasts("Ambulante", client=client)

    assert len(results) == 2
    assert results[0].title == "Radio Ambulante"
    assert results[0].artist == "NPR"
    assert results[0].feed_url == "https://feeds.npr.org/510315/podcast.xml"
    assert results[0].cover_url == "https://example.com/art600.jpg"
    assert results[0].track_count == 150
    assert results[0].genre == "News"

    assert results[1].title == "El Hilo"
    assert results[1].cover_url == "https://example.com/elhilo.jpg"


def test_itunes_search_network_error() -> None:
    def error_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to connect", request=request)

    client = httpx.Client(transport=httpx.MockTransport(error_transport))
    with pytest.raises(AppError) as exc:
        search_itunes_podcasts("Failing Query", client=client)

    assert exc.value.code == ErrorCode.NETWORK
    assert "conexión" in exc.value.user_message.lower()
