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


def test_reconcile_disk_service_and_cli_rf20(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """RF-20: Reconcile scans music_root and marks items with matching [external_id].mp3 as DOWNLOADED."""
    from playlist_sync.core.models import ItemStatus, SourceKind
    from playlist_sync.main import cmd_reconcile
    from playlist_sync.services.sync import reconcile_disk_service

    db_file = tmp_path / "reconcile.db"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)

    src = repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://www.youtube.com/playlist?list=PLreconcile",
        title="My Rock Playlist",
    )
    repo.upsert_item(source_id=src.id, external_id="dQw4w9WgXcQ", title="Track One", position=1)
    it2 = repo.upsert_item(
        source_id=src.id, external_id="9bZkp7q19f0", title="Track Two", position=2
    )
    repo.update_item_status(
        it2.id, status=ItemStatus.ERROR, error_code="NETWORK", error_message="Sin red"
    )
    repo.upsert_item(source_id=src.id, external_id="missing12345", title="Track Three", position=3)

    folder = music_root / src.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    mp3_1 = folder / "Track One [dQw4w9WgXcQ].mp3"
    mp3_2 = folder / "Track Two [9bZkp7q19f0].mp3"
    mp3_4 = folder / "Track Four [newdisk1234].mp3"
    mp3_1.write_bytes(b"ID3DATA1")
    mp3_2.write_bytes(b"ID3DATA2")
    mp3_4.write_bytes(b"ID3DATA4")

    ret = cmd_reconcile(repo=repo, music_root=music_root, source_target="all")
    assert ret == 0
    out = capsys.readouterr().out
    assert "3" in out

    items_by_ext = {it.external_id: it for it in repo.get_items_by_source(src.id)}
    assert items_by_ext["dQw4w9WgXcQ"].status == ItemStatus.DOWNLOADED
    assert items_by_ext["dQw4w9WgXcQ"].file_path == str(mp3_1)

    assert items_by_ext["9bZkp7q19f0"].status == ItemStatus.DOWNLOADED
    assert items_by_ext["9bZkp7q19f0"].file_path == str(mp3_2)
    assert items_by_ext["9bZkp7q19f0"].error_code is None

    assert items_by_ext["newdisk1234"].status == ItemStatus.DOWNLOADED
    assert items_by_ext["newdisk1234"].file_path == str(mp3_4)

    assert items_by_ext["missing12345"].status == ItemStatus.PENDING
    assert items_by_ext["missing12345"].file_path is None

    # Second run is idempotent (0 newly reconciled)
    assert reconcile_disk_service(repo=repo, music_root=music_root) == 0


def test_install_ps1_separates_py_command_and_args_h04() -> None:
    """H-04: install.ps1 must separate executable ('py') and arguments ('-3.12') for PowerShell invocation."""
    root = Path(__file__).resolve().parent.parent.parent
    ps1_text = (root / "install.ps1").read_text(encoding="utf-8")

    assert '"py -3.12"' not in ps1_text
    assert '$pythonExe = "py"' in ps1_text
    assert '@("-3.12")' in ps1_text
    assert "& $pythonExe @pythonArgs -m venv .venv" in ps1_text


def test_cli_doctor_loads_config_toml_h20(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """H-20: CLI 'doctor' must load config.toml before invoking run_doctor."""
    import playlist_sync.main as main_mod

    custom_music = tmp_path / "custom_music_dir"
    monkeypatch.setattr(
        main_mod,
        "load_config",
        lambda *_args, **_kwargs: {
            "storage": {
                "music_root": str(custom_music),
                "min_disk_free_mb": 2048,
            }
        },
    )

    captured: dict[str, object] = {}

    def fake_run_doctor(target_dir: Path | None = None, min_mb: int = 1024) -> bool:
        captured["target_dir"] = target_dir
        captured["min_mb"] = min_mb
        return True

    monkeypatch.setattr(main_mod, "run_doctor", fake_run_doctor)
    monkeypatch.setattr("sys.argv", ["playlist-sync", "doctor"])

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code == 0
    assert captured.get("target_dir") == custom_music
    assert captured.get("min_mb") == 2048
