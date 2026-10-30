"""Integration tests for Podcast support (RF-13, RF-14, Phase 5)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from mutagen.id3 import ID3

from playlist_sync.adapters.composite_source import CompositeSource
from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.api.app import create_app
from playlist_sync.core.models import (
    DownloadedFile,
    RemoteItem,
    SourceInfo,
    SourceKind,
    SourceRecord,
)
from playlist_sync.doctor import SystemDoctor
from playlist_sync.services.sync import add_source_service, sync_source_service
from tests.integration.test_fake_source import FakeSource


def make_mock_doctor() -> SystemDoctor:
    return SystemDoctor(
        python_version=(3, 12, 3),
        which_fn=lambda _: "/bin/mock",
        run_fn=lambda _: (0, "mock version 1.0"),
        ytdlp_version_fn=lambda: "2026.10.26",
        disk_usage_fn=lambda _: (100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        write_test_fn=lambda _: True,
    )


class FakePodcastSource:
    """Mock podcast source that produces valid mock MP3 files."""

    def __init__(self, items: list[RemoteItem] | None = None) -> None:
        self.items = items or []
        self.download_calls: list[str] = []

    def inspect(self, url: str) -> SourceInfo:
        return SourceInfo(
            url=url,
            kind=SourceKind.RSS_PODCAST,
            title="Podcast de Historia",
            cover_url="https://example.com/podcast/cover.jpg",
            item_count=len(self.items),
        )

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        return list(self.items)

    def download(
        self,
        item: RemoteItem,
        dest_dir: Path,
        on_progress: object = None,
    ) -> DownloadedFile:
        self.download_calls.append(item.external_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        from playlist_sync.adapters.repo import sanitize_filename

        clean_name = sanitize_filename(item.title)
        file_path = dest_dir / f"{clean_name} [{item.external_id}].mp3"
        # Minimum valid MP3 with ID3 header
        file_path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90d" * 300)
        return DownloadedFile(
            file_path=file_path,
            external_id=item.external_id,
            title=item.title,
        )


def test_podcast_sync_lifecycle(tmp_path: Path) -> None:
    """Verify podcast synchronization, ID3 tags (genre=Podcast), and newest-first .m3u8."""
    db_file = tmp_path / "podcast.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    library = LocalLibrary(music_root)

    episodes = [
        RemoteItem(
            external_id="ep1",
            title="Episodio 1: Orígenes",
            position=1,
            url="https://example.com/ep1.mp3",
        ),
        RemoteItem(
            external_id="ep2",
            title="Episodio 2: Expansión",
            position=2,
            url="https://example.com/ep2.mp3",
        ),
    ]

    source_adapter = FakePodcastSource(items=episodes)

    # 1. Add podcast source
    source = add_source_service(repo, source_adapter, "https://example.com/feed.xml")
    assert source.kind == SourceKind.RSS_PODCAST
    assert source.title == "Podcast de Historia"

    # 2. Sync podcast source
    result = sync_source_service(
        repo=repo,
        source_adapter=source_adapter,
        source_id=source.id,
        music_root=music_root,
        library=library,
    )
    assert result.downloaded_count == 2
    assert result.skipped_count == 0

    # 3. Verify MP3 files exist and have ID3 tag genre = "Podcast"
    source_dir = music_root / source.folder_name
    ep1_file = source_dir / "Episodio 1 Orígenes [ep1].mp3"
    assert ep1_file.exists()

    tags = ID3(str(ep1_file))
    assert str(tags["TCON"].text[0]) == "Podcast"
    assert str(tags["TALB"].text[0]) == "Podcast de Historia"

    # 4. Verify .m3u8 generated with relative paths
    m3u8_file = source_dir / f"{source.folder_name}.m3u8"
    assert m3u8_file.exists()
    m3u8_content = m3u8_file.read_text(encoding="utf-8")
    assert "#EXTM3U" in m3u8_content
    assert "Episodio 1 Orígenes [ep1].mp3" in m3u8_content
    assert "Episodio 2 Expansión [ep2].mp3" in m3u8_content

    # 5. Idempotent second sync: 0 downloads
    source_adapter.download_calls.clear()
    result2 = sync_source_service(
        repo=repo,
        source_adapter=source_adapter,
        source_id=source.id,
        music_root=music_root,
        library=library,
    )
    assert result2.downloaded_count == 0
    assert result2.skipped_count == 2
    assert len(source_adapter.download_calls) == 0


def test_composite_source_routing() -> None:
    """Verify CompositeSource routes between YouTube and RSS sources."""
    fake_yt = FakeSource(title="YouTube Playlist")
    fake_rss = FakePodcastSource()

    composite = CompositeSource(yt_source=fake_yt, rss_source=fake_rss)

    # YouTube URL routes to yt_source
    info_yt = composite.inspect("https://www.youtube.com/playlist?list=PL123")
    assert info_yt.title == "YouTube Playlist"

    # RSS URL routes to rss_source
    info_rss = composite.inspect("https://feeds.example.com/podcast.rss")
    assert info_rss.kind == SourceKind.RSS_PODCAST
    assert info_rss.title == "Podcast de Historia"


def test_api_podcast_search_endpoint(tmp_path: Path, monkeypatch: object) -> None:
    """Verify GET /podcasts/search endpoint returns podcast results."""
    from playlist_sync.adapters import itunes_search

    # Mock itunes search results
    def fake_search(
        query: str, limit: int = 10, **kwargs: object
    ) -> list[itunes_search.PodcastSearchResult]:
        return [
            itunes_search.PodcastSearchResult(
                title="Podcast de Prueba",
                artist="Autor Prueba",
                feed_url="https://example.com/test_feed.xml",
                cover_url="https://example.com/test_cover.jpg",
                track_count=25,
                genre="Historia",
            )
        ]

    monkeypatch.setattr(
        "playlist_sync.api.routers.podcasts.search_itunes_podcasts",
        fake_search,
    )

    db_file = tmp_path / "api_pod.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource()

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp = client.get("/podcasts/search?q=historia")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Podcast de Prueba"
    assert data[0]["feed_url"] == "https://example.com/test_feed.xml"
