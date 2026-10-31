"""Unit tests for automatic SQLite database backups (Phase 6)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.models import SourceKind
from playlist_sync.services.backup import create_database_backup


def test_database_backup_creates_consistent_copy(tmp_path: Path) -> None:
    db_file = tmp_path / "original.sqlite3"
    repo = SQLiteRepo(db_file)
    repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PLbackup",
        title="Backup Playlist",
    )

    backup_dir = tmp_path / "backups"
    backup_file = create_database_backup(db_file, backup_dir=backup_dir)

    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Verify backup contains the saved source
    conn = sqlite3.connect(str(backup_file))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM sources WHERE url = ?", ("https://youtube.com/playlist?list=PLbackup",)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["title"] == "Backup Playlist"


def test_database_backup_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        create_database_backup(tmp_path / "non_existent.sqlite3")


def test_database_backup_rotation_12_runs_keeps_5_valid_non_empty(tmp_path: Path) -> None:
    """H-02: 12 rotations with max_backups=5 must leave exactly 5 valid, non-empty backups."""
    db_file = tmp_path / "rot.sqlite3"
    repo = SQLiteRepo(db_file)
    backup_dir = tmp_path / "backups"

    for i in range(1, 13):
        repo.add_source(
            kind=SourceKind.YT_PLAYLIST,
            url=f"https://youtube.com/playlist?list=PLrot{i}",
            title=f"Playlist {i}",
        )
        create_database_backup(db_file, backup_dir=backup_dir, max_backups=5)

    backups = sorted(backup_dir.glob("playlist_sync_backup_*.sqlite3"))
    assert len(backups) == 5
    for bkp in backups:
        assert bkp.stat().st_size > 0
        conn = sqlite3.connect(str(bkp))
        count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        conn.close()
        assert count >= 8  # The 5 newest backups correspond to runs 8..12


def test_restore_database_backup_recovers_data_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H-02: restore_database_backup and CLI restore-backup recover lost data."""
    from playlist_sync import main as cli_main
    from playlist_sync.services.backup import restore_database_backup

    db_file = tmp_path / "prod.sqlite3"
    repo = SQLiteRepo(db_file)
    repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PLsaved",
        title="Saved Playlist",
    )

    backup_dir = tmp_path / "backups"
    backup_file = create_database_backup(db_file, backup_dir=backup_dir, max_backups=5)

    # Simulate accidental data loss / corruption by creating an empty DB
    corrupted_db = tmp_path / "restored.sqlite3"
    SQLiteRepo(corrupted_db)
    assert len(SQLiteRepo(corrupted_db).list_sources()) == 0

    # Restore via function
    restored_path = restore_database_backup(backup_file, corrupted_db)
    assert restored_path == corrupted_db.resolve()
    restored_sources = SQLiteRepo(corrupted_db).list_sources()
    assert len(restored_sources) == 1
    assert restored_sources[0].title == "Saved Playlist"

    # Also test CLI command `restore-backup`
    cli_target_db = tmp_path / "cli_restored.sqlite3"
    monkeypatch.setattr(
        cli_main,
        "load_config",
        lambda: {"storage": {"database_path": str(cli_target_db), "music_root": str(tmp_path)}},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["playlist-sync", "restore-backup", str(backup_file)],
    )
    with pytest.raises(SystemExit) as exc:
        cli_main.main()
    assert exc.value.code == 0
    cli_sources = SQLiteRepo(cli_target_db).list_sources()
    assert len(cli_sources) == 1
    assert cli_sources[0].title == "Saved Playlist"


def test_backup_guard_rejects_music_root_and_external_files(tmp_path: Path) -> None:
    """H-02: Backups cannot live in music_root and guard rejects files outside backup_dir."""
    from playlist_sync.services.backup import _verify_backup_deletion_guard

    db_file = tmp_path / "db.sqlite3"
    SQLiteRepo(db_file)

    with pytest.raises(ValueError, match="music_root"):
        create_database_backup(db_file, backup_dir=tmp_path / "music_root")

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    outside_file = tmp_path / "playlist_sync_backup_outside.sqlite3"
    outside_file.write_bytes(b"123")
    with pytest.raises(ValueError, match="Guard violation"):
        _verify_backup_deletion_guard(outside_file, backup_dir)

    non_backup = backup_dir / "Song [id].mp3"
    non_backup.write_bytes(b"123")
    with pytest.raises(ValueError, match="Guard violation"):
        _verify_backup_deletion_guard(non_backup, backup_dir)
