"""Unit tests for the RSS Source Adapter (RF-13)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from playlist_sync.adapters.rss_source import RssSource
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    Progress,
    RemoteItem,
    SourceKind,
    SourceRecord,
    SourceStatus,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_rss_inspect_valid_feed() -> None:
    xml_content = (FIXTURES_DIR / "valid_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    info = source.inspect("https://example.com/podcast.xml")
    assert info.title == "Charlas de Tecnología"
    assert info.kind == SourceKind.RSS_PODCAST
    assert info.cover_url == "https://example.com/podcast/cover.jpg"
    assert info.item_count == 2


def test_rss_list_items_valid_feed() -> None:
    xml_content = (FIXTURES_DIR / "valid_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    src_record = SourceRecord(
        id=1,
        kind=SourceKind.RSS_PODCAST,
        url="https://example.com/podcast.xml",
        title="Charlas de Tecnología",
        cover_url=None,
        folder_name="Charlas",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=None,  # type: ignore[arg-type]
    )

    items = source.list_items(src_record)
    assert len(items) == 2
    assert items[0].title == "Episodio 2: Agentes y Modelos de Lenguaje"
    assert items[0].external_id == "ep-002-agentes"
    assert items[0].url == "https://example.com/audio/ep2.mp3"
    assert items[0].published_at is not None
    assert items[0].duration_seconds == 1800

    assert items[1].title == "Episodio 1: Bienvenidos al podcast"
    assert items[1].duration_seconds == 1200


def test_rss_inspect_no_cover() -> None:
    xml_content = (FIXTURES_DIR / "no_cover_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    info = source.inspect("https://example.com/no-cover.xml")
    assert info.title == "Podcast Sin Portada"
    assert info.cover_url is None
    assert info.item_count == 1


def test_rss_list_items_weird_enclosures() -> None:
    xml_content = (FIXTURES_DIR / "weird_enclosure_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    src_record = SourceRecord(
        id=2,
        kind=SourceKind.RSS_PODCAST,
        url="https://example.com/weird.xml",
        title="Weird",
        cover_url=None,
        folder_name="Weird",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=None,  # type: ignore[arg-type]
    )

    items = source.list_items(src_record)
    assert len(items) == 2
    assert "token=xyz123" in items[0].url
    assert "media_fallback.mp3" in items[1].url


def test_rss_download_enclosure(tmp_path: Path) -> None:
    audio_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90d" * 500

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=audio_bytes,
            headers={"Content-Length": str(len(audio_bytes))},
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    item = RemoteItem(
        external_id="ep123",
        title="Podcast Audio Ep 1",
        position=1,
        url="https://example.com/ep1.mp3",
    )

    progress_events: list[Progress] = []
    dest_dir = tmp_path / "episodes"

    downloaded = source.download(item, dest_dir, on_progress=progress_events.append)
    assert downloaded.file_path.exists()
    assert downloaded.file_path.name == "Podcast Audio Ep 1 [ep123].mp3"
    assert len(progress_events) >= 1
    assert progress_events[-1].percentage == 100.0

    # Idempotent second call: doesn't re-download
    progress_events.clear()
    downloaded2 = source.download(item, dest_dir, on_progress=progress_events.append)
    assert downloaded2.file_path == downloaded.file_path
    assert len(progress_events) == 1
    assert progress_events[0].status == "finished"


def test_rss_errors_invalid_feed() -> None:
    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"Not valid XML <<>>")

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    with pytest.raises(AppError) as exc:
        source.inspect("https://example.com/bad.xml")
    assert exc.value.code == ErrorCode.INVALID_URL


def test_rss_errors_http_404() -> None:
    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    with pytest.raises(AppError) as exc:
        source.inspect("https://example.com/notfound.xml")
    assert exc.value.code == ErrorCode.SOURCE_NOT_FOUND
