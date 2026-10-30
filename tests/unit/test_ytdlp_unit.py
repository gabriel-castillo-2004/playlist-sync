"""Unit tests for YtDlpSource with mocked yt-dlp library (offline)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from playlist_sync.adapters.ytdlp_source import (
    YtDlpSource,
    find_ffmpeg_location,
    validate_youtube_url,
)
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    Progress,
    RemoteItem,
    SourceKind,
    SourceRecord,
    SourceStatus,
)


def test_validate_youtube_url_valid() -> None:
    valid_urls = [
        "https://www.youtube.com/playlist?list=PL12345",
        "https://music.youtube.com/playlist?list=PL67890",
        "https://youtu.be/playlist?list=PLabc",
    ]
    for u in valid_urls:
        validate_youtube_url(u)


def test_validate_youtube_url_invalid() -> None:
    invalid_urls = [
        "ftp://youtube.com/playlist",
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "https://evil-site.com/video",
        "not_a_url",
    ]
    for u in invalid_urls:
        with pytest.raises(AppError) as exc:
            validate_youtube_url(u)
        assert exc.value.code == ErrorCode.INVALID_URL


def test_find_ffmpeg_location() -> None:
    loc = find_ffmpeg_location()
    assert loc is None or isinstance(loc, str)


def test_ytdlp_inspect_mocked() -> None:
    adapter = YtDlpSource()
    fake_info = {
        "title": "Mocked Playlist",
        "thumbnail": "http://img.jpg",
        "entries": [{"id": "1"}, {"id": "2"}],
    }
    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = fake_info
        mock_ydl_cls.return_value = mock_ydl

        info = adapter.inspect("https://youtube.com/playlist?list=PLmock")
        assert info.title == "Mocked Playlist"
        assert info.cover_url == "http://img.jpg"
        assert info.item_count == 2
        assert info.kind == SourceKind.YT_PLAYLIST


def test_ytdlp_inspect_empty_info() -> None:
    adapter = YtDlpSource()
    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = None
        mock_ydl_cls.return_value = mock_ydl

        with pytest.raises(AppError) as exc:
            adapter.inspect("https://youtube.com/playlist?list=PLempty")
        assert exc.value.code == ErrorCode.SOURCE_NOT_FOUND


def test_ytdlp_list_items_mocked() -> None:
    adapter = YtDlpSource()
    source_rec = SourceRecord(
        id=1,
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PLmock",
        title="Mocked",
        cover_url=None,
        folder_name="Mocked",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=datetime.now(),
    )
    fake_info = {
        "entries": [
            {"id": "v1", "title": "Track 1", "upload_date": "20240101", "duration": 180},
            {"id": "v2", "title": "[Deleted video]"},
            None,
            {"id": "v3", "title": "Track 3", "duration": 200},
        ]
    }
    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = fake_info
        mock_ydl_cls.return_value = mock_ydl

        items = adapter.list_items(source_rec)
        assert len(items) == 2
        assert items[0].external_id == "v1"
        assert items[0].position == 1
        assert items[1].external_id == "v3"
        assert items[1].position == 2


def test_ytdlp_download_mocked(tmp_path: Path) -> None:
    adapter = YtDlpSource()
    item = RemoteItem(
        external_id="v_dl",
        title="Download Me",
        position=1,
        url="https://youtube.com/watch?v=v_dl",
    )
    dest_dir = tmp_path / "music"
    expected_file = dest_dir / "Download Me [v_dl].mp3"

    progress_events: list[Progress] = []

    def mock_download(urls: list[str]) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        expected_file.write_text("AUDIO_DATA", encoding="utf-8")

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.download.side_effect = mock_download
        mock_ydl_cls.return_value = mock_ydl

        res = adapter.download(item, dest_dir, on_progress=progress_events.append)
        assert res.file_path == expected_file
        assert res.external_id == "v_dl"
