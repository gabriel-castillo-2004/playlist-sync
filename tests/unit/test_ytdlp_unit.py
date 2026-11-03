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
            {
                "id": "v1",
                "title": "Track 1",
                "upload_date": "20240101",
                "duration": 180,
                "uploader": "Canal Uno",
            },
            {"id": "v2", "title": "[Deleted video]"},
            None,
            {"id": "v3", "title": "Track 3", "duration": 200, "channel": "Canal Tres"},
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
        assert items[0].artist == "Canal Uno"
        assert items[1].external_id == "v3"
        assert items[1].position == 2
        assert items[1].artist == "Canal Tres"


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


def test_ytdlp_download_fallback_locates_mp3_by_real_11char_external_id(tmp_path: Path) -> None:
    """H-14: Fallback lookup must find ' [external_id].mp3' literally, not as a glob char class."""
    adapter = YtDlpSource()
    real_id = "dQw4w9WgXcQ"  # 11-char YouTube video ID
    item = RemoteItem(
        external_id=real_id,
        title="Canción Original",
        position=1,
        url=f"https://www.youtube.com/watch?v={real_id}",
    )
    dest_dir = tmp_path / "music"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Unrelated file ending in 'Q.mp3' that a broken glob '*[dQw4w9WgXcQ].mp3' would match
    decoy_file = dest_dir / "Otra cancion Q.mp3"
    decoy_file.write_bytes(b"DECOY")

    # Simulate yt-dlp slightly altering the title when writing the MP3
    actual_downloaded_mp3 = dest_dir / f"Cancion Original Normalizada [{real_id}].mp3"

    def mock_download(urls: list[str]) -> None:
        actual_downloaded_mp3.write_bytes(b"REAL_MP3_DATA")

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.download.side_effect = mock_download
        mock_ydl_cls.return_value = mock_ydl

        res = adapter.download(item, dest_dir)
        assert res.file_path == actual_downloaded_mp3
        assert res.file_path != decoy_file


def test_ytdlp_default_extra_and_ejs_dependency_configured() -> None:
    """H-08 (deps): Verify yt-dlp[default] is configured across project files and yt_dlp_ejs is installed."""
    import importlib.util

    root = Path(__file__).resolve().parent.parent.parent
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    start_sh_text = (root / "start.sh").read_text(encoding="utf-8")
    start_bat_text = (root / "start.bat").read_text(encoding="utf-8")
    service_text = (root / "systemd" / "playlist-sync.service").read_text(encoding="utf-8")

    assert "yt-dlp[default]" in pyproject_text
    assert "yt-dlp[default]" in start_sh_text
    assert "yt-dlp[default]" in start_bat_text
    assert "yt-dlp[default]" in service_text
    assert importlib.util.find_spec("yt_dlp_ejs") is not None


def test_systemd_service_and_installer_h08_configuration(tmp_path: Path) -> None:
    """H-08 (resto): Verify systemd service includes ~/.deno/bin in PATH and install-service.sh substitutes repo path dynamically."""
    import subprocess

    root = Path(__file__).resolve().parent.parent.parent
    service_file = root / "systemd" / "playlist-sync.service"
    installer_file = root / "systemd" / "install-service.sh"

    service_text = service_file.read_text(encoding="utf-8")

    # 1. playlist-sync.service must define PATH with ~/.deno/bin (%h/.deno/bin)
    assert 'Environment="PATH=%h/.deno/bin:/usr/local/bin:/usr/bin:/bin"' in service_text

    # 2. install-service.sh must substitute repo path dynamically
    installer_text = installer_file.read_text(encoding="utf-8")
    assert "sed " in installer_text

    # 3. Run install-service.sh with overridden REPO_DIR and USER_SYSTEMD_DIR
    custom_repo_dir = "/opt/custom-proyectos/playlist-sync"
    custom_systemd_user_dir = tmp_path / "systemd_user"
    custom_systemd_user_dir.mkdir(parents=True, exist_ok=True)

    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "REPO_DIR": custom_repo_dir,
        "USER_SYSTEMD_DIR": str(custom_systemd_user_dir),
        "INSTALL_SERVICE_ONLY": "1",
    }
    result = subprocess.run(
        ["bash", str(installer_file)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0

    installed_service_file = custom_systemd_user_dir / "playlist-sync.service"
    assert installed_service_file.exists()
    installed_text = installed_service_file.read_text(encoding="utf-8")

    assert f"WorkingDirectory={custom_repo_dir}" in installed_text
    assert f"ExecStartPre=-{custom_repo_dir}/.venv/bin/pip" in installed_text
    assert f"ExecStart={custom_repo_dir}/.venv/bin/python" in installed_text
    assert "%h/playlist-sync" not in installed_text
    assert 'Environment="PATH=%h/.deno/bin:/usr/local/bin:/usr/bin:/bin"' in installed_text


def test_ytdlp_sleep_intervals_and_config_h17(tmp_path: Path) -> None:
    """H-17: YtDlpSource configures sleep_interval and sleep_interval_requests from config.toml."""
    import tomllib

    root = Path(__file__).resolve().parent.parent.parent
    cfg = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
    sync_cfg = cfg["sync"]

    assert "sleep_interval" in sync_cfg
    assert "sleep_interval_requests" in sync_cfg
    assert float(sync_cfg["sleep_interval"]) > 0
    assert float(sync_cfg["sleep_interval_requests"]) > 0

    adapter = YtDlpSource(
        rate_limit_bytes=512_000,
        sleep_interval=float(sync_cfg["sleep_interval"]),
        sleep_interval_requests=float(sync_cfg["sleep_interval_requests"]),
    )
    item = RemoteItem(
        external_id="v_h17",
        title="Sleep Test Track",
        position=1,
        url="https://www.youtube.com/watch?v=v_h17",
    )
    dest_dir = tmp_path / "music_h17"
    expected_file = dest_dir / "Sleep Test Track [v_h17].mp3"

    captured_opts: dict[str, object] = {}

    def fake_ydl_init(opts: dict[str, object]) -> MagicMock:
        captured_opts.update(opts)
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl

        def _dl(urls: list[str]) -> None:
            dest_dir.mkdir(parents=True, exist_ok=True)
            expected_file.write_bytes(b"MP3")

        mock_ydl.download.side_effect = _dl
        return mock_ydl

    with patch("yt_dlp.YoutubeDL", side_effect=fake_ydl_init):
        adapter.download(item, dest_dir)

    assert captured_opts.get("sleep_interval") == float(sync_cfg["sleep_interval"])
    assert captured_opts.get("sleep_interval_requests") == float(
        sync_cfg["sleep_interval_requests"]
    )
    assert captured_opts.get("ratelimit") == 512_000


def test_auto_update_ytdlp_online_and_offline_h17(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """H-17 / RF-16: auto_update_ytdlp in main.py logs outcome with and without network."""
    import logging
    import subprocess

    from playlist_sync.main import auto_update_ytdlp

    # 1. Simulated online success
    def mock_run_ok(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "yt-dlp[default]" in cmd
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="Successfully installed yt-dlp", stderr=""
        )

    with caplog.at_level(logging.INFO):
        caplog.clear()
        ok = auto_update_ytdlp(run_fn=mock_run_ok)
        assert ok is True
        assert any("yt-dlp" in rec.message.lower() for rec in caplog.records)

    # 2. Simulated offline failure (nonzero returncode)
    def mock_run_offline(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="WARNING: Retrying... NewConnectionError: Failed to establish a new connection",
        )

    with caplog.at_level(logging.WARNING):
        caplog.clear()
        ok_off = auto_update_ytdlp(run_fn=mock_run_offline)
        assert ok_off is False
        assert any(
            rec.levelname == "WARNING" and "yt-dlp" in rec.message.lower() for rec in caplog.records
        )
