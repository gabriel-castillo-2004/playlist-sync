"""Automatic SQLite database backup utility (Phase 6)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _verify_backup_deletion_guard(candidate: Path, backup_dir: Path) -> Path:
    """Ensure a file to be pruned is strictly a SQLite backup inside backup_dir."""
    resolved_dir = backup_dir.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate.parent != resolved_dir:
        raise ValueError(
            f"Guard violation: {resolved_candidate} is not directly inside {resolved_dir}"
        )
    if (
        not resolved_candidate.name.startswith("playlist_sync_backup_")
        or resolved_candidate.suffix != ".sqlite3"
    ):
        raise ValueError(
            f"Guard violation: {resolved_candidate.name} is not a recognized SQLite backup file"
        )
    return resolved_candidate


def create_database_backup(
    db_path: Path | str,
    backup_dir: Path | str = "backups",
    max_backups: int = 5,
) -> Path:
    """Create a consistent online backup of the SQLite database.

    Uses SQLite's online backup API (conn.backup) to safely copy the database
    while it may be in use. Keeps up to max_backups valid, non-empty files in backup_dir.
    """
    source_db = Path(db_path).resolve()
    if not source_db.exists():
        raise FileNotFoundError(f"Database file does not exist: {source_db}")

    target_dir = Path(backup_dir).resolve()
    if target_dir.name.lower() == "music_root":
        raise ValueError("Database backups cannot be stored inside music_root.")
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    backup_file = target_dir / f"playlist_sync_backup_{timestamp}.sqlite3"
    seq = 1
    while backup_file.exists():
        backup_file = target_dir / f"playlist_sync_backup_{timestamp}_{seq}.sqlite3"
        seq += 1

    src_conn = sqlite3.connect(str(source_db))
    dst_conn = sqlite3.connect(str(backup_file))
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
        logger.info("Created database backup at %s", backup_file)
    finally:
        dst_conn.close()
        src_conn.close()

    # Rotate old backups safely inside target_dir only
    if max_backups > 0:
        try:
            backups = sorted(
                target_dir.glob("playlist_sync_backup_*.sqlite3"),
                key=lambda p: (p.stat().st_mtime_ns, p.name),
            )
            while len(backups) > max_backups:
                oldest = backups.pop(0)
                verified_path = _verify_backup_deletion_guard(oldest, target_dir)
                verified_path.unlink()
        except Exception as exc:
            logger.warning("Could not prune old database backups: %s", exc)

    return backup_file


def restore_database_backup(
    backup_file: Path | str,
    db_path: Path | str,
) -> Path:
    """Restore the SQLite database from a backup file using SQLite's online backup API."""
    source_backup = Path(backup_file).resolve()
    if not source_backup.exists():
        raise FileNotFoundError(f"Backup file does not exist: {source_backup}")
    if source_backup.stat().st_size == 0:
        raise ValueError(f"Backup file is empty (0 bytes): {source_backup}")

    target_db = Path(db_path).resolve()
    target_db.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(source_backup))
    dst_conn = sqlite3.connect(str(target_db))
    try:
        check = src_conn.execute("PRAGMA integrity_check;").fetchone()
        if not check or check[0] != "ok":
            raise ValueError(f"Backup file failed SQLite integrity check: {source_backup}")
        with dst_conn:
            src_conn.backup(dst_conn)
        logger.info("Restored database from %s to %s", source_backup, target_db)
    finally:
        dst_conn.close()
        src_conn.close()

    return target_db
