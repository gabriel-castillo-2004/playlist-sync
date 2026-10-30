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
