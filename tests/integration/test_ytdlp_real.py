"""Real network integration tests using yt-dlp against live playlists.

These tests are marked @pytest.mark.network and disabled by default in standard test runs.
"""

from datetime import datetime
from pathlib import Path

import pytest

from playlist_sync.adapters.ytdlp_source import YtDlpSource
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import SourceKind, SourceRecord, SourceStatus


@pytest.mark.network
def test_real_inspect_public_playlist() -> None:
    source_adapter = YtDlpSource()
    url = "https://music.youtube.com/playlist?list=PLH4CG4U26Tr0"
    info = source_adapter.inspect(url)
    assert info.title == "Salsitas"
    assert info.item_count is not None and info.item_count > 0


@pytest.mark.network
def test_real_private_or_nonexistent_playlist() -> None:
    source_adapter = YtDlpSource()
    url = "https://www.youtube.com/playlist?list=PL_NON_EXISTENT_PLAYLIST_12345"
    with pytest.raises(AppError) as exc:
        source_adapter.inspect(url)
    assert exc.value.code in (ErrorCode.SOURCE_NOT_FOUND, ErrorCode.PRIVATE_SOURCE)


@pytest.mark.network
def test_real_list_items_and_download_first(tmp_path: Path) -> None:
    """Download the first track from user's test playlist to verify yt-dlp + ffmpeg pipeline."""
    source_adapter = YtDlpSource()
    url = "https://music.youtube.com/playlist?list=PLH4CG4U26Tr0"
    source_rec = SourceRecord(
        id=1,
        kind=SourceKind.YT_PLAYLIST,
        url=url,
        title="Salsitas",
        cover_url=None,
        folder_name="Salsitas",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=datetime.now(),
    )
    items = source_adapter.list_items(source_rec)
    assert len(items) > 0
    first_item = items[0]
    assert first_item.external_id is not None

    dest_dir = tmp_path / "downloads"
    downloaded = source_adapter.download(first_item, dest_dir)
    assert downloaded.file_path.exists()
    assert downloaded.file_path.suffix == ".mp3"
    assert downloaded.file_path.stat().st_size > 0
