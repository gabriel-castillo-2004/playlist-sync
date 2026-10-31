"""Real network integration tests using yt-dlp against live playlists.

These tests are marked @pytest.mark.network and disabled by default in standard test runs.
"""

from pathlib import Path

import pytest
from mutagen.id3 import ID3

from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.adapters.ytdlp_source import YtDlpSource
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import RemoteItem, SourceRecord
from playlist_sync.services.sync import add_source_service, sync_source_service

PUBLIC_PLAYLIST_URLS = [
    "https://music.youtube.com/playlist?list=PLH4CG4U26Tr0",
    "https://music.youtube.com/playlist?list=PLbB-sT_tcH7s",
]


class SingleTrackRealYtDlpSource(YtDlpSource):
    """Real YtDlpSource that limits list_items to the first remote track for fast E2E testing."""

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        items = super().list_items(source)
        assert len(items) > 0
        return items[:1]


@pytest.mark.network
@pytest.mark.parametrize("url", PUBLIC_PLAYLIST_URLS)
def test_real_inspect_public_playlist(url: str) -> None:
    source_adapter = YtDlpSource()
    info = source_adapter.inspect(url)
    assert info.title
    assert info.item_count is not None and info.item_count > 0


@pytest.mark.network
def test_real_private_or_nonexistent_playlist() -> None:
    source_adapter = YtDlpSource()
    url = "https://www.youtube.com/playlist?list=PL_NON_EXISTENT_PLAYLIST_12345"
    with pytest.raises(AppError) as exc:
        source_adapter.inspect(url)
    assert exc.value.code in (ErrorCode.SOURCE_NOT_FOUND, ErrorCode.PRIVATE_SOURCE)


@pytest.mark.network
def test_real_sync_download_id3_cover_and_idempotency(tmp_path: Path) -> None:
    """Verify full real download, [external_id] naming, cover + ID3 tags, and 2nd-run idempotency."""
    db_path = tmp_path / "test_real.db"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_path)
    library = LocalLibrary(music_root)
    source_adapter = SingleTrackRealYtDlpSource()

    url = PUBLIC_PLAYLIST_URLS[0]
    source_rec = add_source_service(repo, source_adapter, url)

    # First run: downloads 1 real track, embeds cover + ID3 tags, builds .m3u8
    res1 = sync_source_service(
        repo=repo,
        source_adapter=source_adapter,
        source_id=source_rec.id,
        music_root=music_root,
        library=library,
        min_free_mb=10,
    )
    assert res1.total_remote == 1
    assert res1.downloaded_count == 1
    assert res1.skipped_count == 0
    assert res1.failed_count == 0

    items = repo.get_items_by_source(source_rec.id)
    assert len(items) == 1
    db_item = items[0]
    assert db_item.external_id and len(db_item.external_id) == 11
    assert db_item.file_path is not None

    mp3_path = Path(db_item.file_path)
    assert mp3_path.exists()
    assert mp3_path.name.endswith(f"[{db_item.external_id}].mp3")
    assert mp3_path.stat().st_size > 0

    # Verify ID3v2.3 tags and embedded cover (APIC)
    tags = ID3(str(mp3_path))
    assert "TIT2" in tags and str(tags["TIT2"].text[0])
    assert "TPE1" in tags and str(tags["TPE1"].text[0])
    assert "TALB" in tags and str(tags["TALB"].text[0]) == source_rec.title
    assert "TRCK" in tags and str(tags["TRCK"].text[0]) == "1/1"
    apic_frames = tags.getall("APIC")
    assert len(apic_frames) == 1
    assert len(apic_frames[0].data) > 0

    # Verify .m3u8 exists and uses relative path
    m3u8_path = music_root / source_rec.folder_name / f"{source_rec.folder_name}.m3u8"
    assert m3u8_path.exists()
    m3u8_text = m3u8_path.read_text(encoding="utf-8")
    assert mp3_path.name in m3u8_text

    # Second run: strictly idempotent (0 downloaded, 1 skipped)
    res2 = sync_source_service(
        repo=repo,
        source_adapter=source_adapter,
        source_id=source_rec.id,
        music_root=music_root,
        library=library,
        min_free_mb=10,
    )
    assert res2.total_remote == 1
    assert res2.downloaded_count == 0
    assert res2.skipped_count == 1
    assert res2.failed_count == 0
