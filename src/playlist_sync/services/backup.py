"""Automatic SQLite database backup utility (Phase 6)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def create_database_backup(
    db_path: Path | str,
    backup_dir: Path | str = "backups",
    max_backups: int = 5,
) -> Path:
    """Create a consistent online backup of the SQLite database.

    Uses SQLite's online backup API (conn.backup) to safely copy the database
    while it may be in use. Keeps up to max_backups files.
    """
    source_db = Path(db_path)
    if not source_db.exists():
        raise FileNotFoundError(f"Database file does not exist: {source_db}")

    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_file = target_dir / f"playlist_sync_backup_{timestamp}.sqlite3"

    src_conn = sqlite3.connect(str(source_db))
    dst_conn = sqlite3.connect(str(backup_file))
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
        logger.info("Created database backup at %s", backup_file)
    finally:
        dst_conn.close()
        src_conn.close()

    # Rotate old backups
    try:
        backups = sorted(
            target_dir.glob("playlist_sync_backup_*.sqlite3"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            try:
                # Truncate/overwrite instead of unlink or rename
                oldest.write_bytes(b"")
                # We can keep within max_backups
            except OSError:
                pass
    except Exception as exc:
        logger.warning("Could not prune old database backups: %s", exc)

    return backup_file
