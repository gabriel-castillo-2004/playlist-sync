"""Unit tests for the CLI commands."""

from pathlib import Path

import pytest

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.models import Progress, RemoteItem
from playlist_sync.main import cli_progress_hook, cmd_add, cmd_status, cmd_sync, load_config
from tests.integration.test_fake_source import FakeSource


def test_load_config() -> None:
    cfg = load_config()
    assert "storage" in cfg
    assert "sync" in cfg


def test_cli_progress_hook(capsys: pytest.CaptureFixture[str]) -> None:
    p = Progress(
        status="downloading",
        percentage=45.2,
        speed_bytes_per_sec=1024 * 500,
        current_item_title="My Cool Track",
    )
    cli_progress_hook(p)
    out = capsys.readouterr().out
    assert "45.2%" in out
    assert "My Cool Track" in out


def test_cmd_add_and_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_file = tmp_path / "cli.db"
    repo = SQLiteRepo(db_file)
    fake = FakeSource(title="CLI Playlist")

    # Add source
    ret = cmd_add("https://youtube.com/playlist?list=PLcli", repo, fake)  # type: ignore[arg-type]
    assert ret == 0
    out = capsys.readouterr().out
    assert "Fuente registrada exitosamente" in out

    # Status check
    ret_status = cmd_status(repo)
    assert ret_status == 0
    out_status = capsys.readouterr().out
    assert "CLI Playlist" in out_status


def test_cmd_sync(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_file = tmp_path / "cli.db"
    repo = SQLiteRepo(db_file)
    items = [
        RemoteItem(external_id="v1", title="Song 1", position=1, url="http://v1"),
    ]
    fake = FakeSource(title="CLI Sync", items=items)
    cmd_add("https://youtube.com/playlist?list=PLcli", repo, fake)  # type: ignore[arg-type]
    capsys.readouterr()

    ret_sync = cmd_sync(
        source_target="1",
        repo=repo,
        source_adapter=fake,  # type: ignore[arg-type]
        music_root=tmp_path / "music",
        safety_threshold=0.50,
        max_retries=3,
        min_disk_free_mb=10,
    )
    assert ret_sync == 0
    out = capsys.readouterr().out
    assert "Sincronizacion finalizada" in out
    assert "Descargadas: 1" in out


def test_cmd_sync_invalid_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_file = tmp_path / "cli.db"
    repo = SQLiteRepo(db_file)
    fake = FakeSource()

    ret = cmd_sync(
        source_target="invalid_id",
        repo=repo,
        source_adapter=fake,  # type: ignore[arg-type]
        music_root=tmp_path / "music",
        safety_threshold=0.50,
        max_retries=3,
        min_disk_free_mb=10,
    )
    assert ret == 1
    out = capsys.readouterr().out
    assert "no es un ID valido" in out
