"""SQLite repository and schema migrations (Section 6.1)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from playlist_sync.core.models import (
    ItemRecord,
    ItemStatus,
    SourceKind,
    SourceRecord,
    SourceStatus,
)

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    cover_url TEXT,
    folder_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    last_sync_at TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    last_known_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    position INTEGER NOT NULL,
    published_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_code TEXT,
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    file_path TEXT,
    downloaded_at TEXT,
    removed_remote INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_items_source_status ON items(source_id, status);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Sanitize directory or file name across Windows and Linux.

    Strips reserved characters (<>:"/\\|?*), control chars, and trailing dots/spaces.
    """
    # Replace illegal filesystem characters with space
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    # Collapse consecutive spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length].rstrip(". ")


class SQLiteRepo:
    """Repository handling SQLite database connection and operations."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Run database migrations."""
        with self._conn() as conn:
            conn.executescript(SCHEMA_V1)
            row = conn.execute("SELECT version FROM schema_version WHERE version = 1;").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (1, ?);",
                    (datetime.now(UTC).isoformat(),),
                )
            cols = {
                col_row["name"] for col_row in conn.execute("PRAGMA table_info(items);").fetchall()
            }
            if "artist" not in cols:
                conn.execute("ALTER TABLE items ADD COLUMN artist TEXT;")

    # -------------------------------------------------------------------------
    # Sources CRUD
    # -------------------------------------------------------------------------

    def add_source(
        self,
        kind: SourceKind,
        url: str,
        title: str,
        cover_url: str | None = None,
        folder_name: str | None = None,
    ) -> SourceRecord:
        """Add a new source to track."""
        now = datetime.now(UTC).isoformat()
        clean_folder = folder_name or sanitize_filename(title)

        with self._conn() as conn:
            # Check folder collision (case-insensitive)
            rows = conn.execute("SELECT folder_name FROM sources;").fetchall()
            existing_folders = {r["folder_name"].lower() for r in rows}
            unique_folder = clean_folder
            counter = 1
            while unique_folder.lower() in existing_folders:
                unique_folder = f"{clean_folder} ({counter})"
                counter += 1

            cursor = conn.execute(
                """
                INSERT INTO sources (
                    kind, url, title, cover_url, folder_name,
                    status, last_known_count, created_at
                ) VALUES (?, ?, ?, ?, ?, 'idle', 0, ?);
                """,
                (kind.value, url, title, cover_url, unique_folder, now),
            )
            source_id = cursor.lastrowid
            assert source_id is not None
            row = conn.execute("SELECT * FROM sources WHERE id = ?;", (source_id,)).fetchone()
            assert row is not None
            return self._row_to_source(row)

    def get_source(self, source_id: int) -> SourceRecord | None:
        """Retrieve a source by ID."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?;", (source_id,)).fetchone()
            return self._row_to_source(row) if row else None

    def get_source_by_url(self, url: str) -> SourceRecord | None:
        """Retrieve a source by exact URL."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM sources WHERE url = ?;", (url,)).fetchone()
            return self._row_to_source(row) if row else None

    def list_sources(self) -> list[SourceRecord]:
        """List all tracked sources."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM sources ORDER BY id ASC;").fetchall()
            return [self._row_to_source(r) for r in rows]

    def update_source_status(
        self,
        source_id: int,
        status: SourceStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        last_known_count: int | None = None,
    ) -> None:
        """Update synchronization status of a source."""
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            if last_known_count is not None:
                conn.execute(
                    """
                    UPDATE sources
                    SET status = ?, last_error_code = ?, last_error_message = ?,
                        last_sync_at = ?, last_known_count = ?
                    WHERE id = ?;
                    """,
                    (status.value, error_code, error_message, now, last_known_count, source_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE sources
                    SET status = ?, last_error_code = ?, last_error_message = ?,
                        last_sync_at = ?
                    WHERE id = ?;
                    """,
                    (status.value, error_code, error_message, now, source_id),
                )

    def update_source_metadata(
        self,
        source_id: int,
        title: str,
        cover_url: str | None = None,
    ) -> None:
        """Update title or cover URL of a source."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE sources SET title = ?, cover_url = COALESCE(?, cover_url) WHERE id = ?;",
                (title, cover_url, source_id),
            )

    # -------------------------------------------------------------------------
    # Items CRUD
    # -------------------------------------------------------------------------

    def upsert_item(
        self,
        source_id: int,
        external_id: str,
        title: str,
        position: int,
        published_at: datetime | None = None,
        artist: str | None = None,
    ) -> ItemRecord:
        """Insert or update position/title of an item without resetting download status."""
        pub_str = published_at.isoformat() if published_at else None
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO items (
                    source_id, external_id, title, artist, position, published_at,
                    status, attempts, removed_remote
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, 0)
                ON CONFLICT(source_id, external_id) DO UPDATE SET
                    title = excluded.title,
                    artist = COALESCE(excluded.artist, items.artist),
                    position = excluded.position,
                    published_at = COALESCE(excluded.published_at, items.published_at),
                    removed_remote = 0;
                """,
                (source_id, external_id, title, artist, position, pub_str),
            )
            row = conn.execute(
                "SELECT * FROM items WHERE source_id = ? AND external_id = ?;",
                (source_id, external_id),
            ).fetchone()
            assert row is not None
            return self._row_to_item(row)

    def get_item(self, item_id: int) -> ItemRecord | None:
        """Retrieve an item by ID."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?;", (item_id,)).fetchone()
            return self._row_to_item(row) if row else None

    def get_items_by_source(self, source_id: int) -> list[ItemRecord]:
        """Retrieve all items belonging to a source, sorted by position."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM items WHERE source_id = ? ORDER BY position ASC;",
                (source_id,),
            ).fetchall()
            return [self._row_to_item(r) for r in rows]

    def update_item_status(
        self,
        item_id: int,
        status: ItemStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        file_path: str | None = None,
        increment_attempts: bool = False,
    ) -> None:
        """Update an item's status, error info or file path."""
        now = datetime.now(UTC).isoformat() if status == ItemStatus.DOWNLOADED else None
        with self._conn() as conn:
            if increment_attempts:
                conn.execute(
                    """
                    UPDATE items
                    SET status = ?, error_code = ?, error_message = ?,
                        file_path = COALESCE(?, file_path),
                        downloaded_at = COALESCE(?, downloaded_at),
                        attempts = attempts + 1
                    WHERE id = ?;
                    """,
                    (status.value, error_code, error_message, file_path, now, item_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE items
                    SET status = ?, error_code = ?, error_message = ?,
                        file_path = COALESCE(?, file_path),
                        downloaded_at = COALESCE(?, downloaded_at)
                    WHERE id = ?;
                    """,
                    (status.value, error_code, error_message, file_path, now, item_id),
                )

    def mark_item_removed_remote(self, item_id: int) -> None:
        """Mark an item as removed from the remote source (never deleting the file)."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE items SET removed_remote = 1 WHERE id = ?;",
                (item_id,),
            )

    def restore_item_removed_remote(self, item_id: int) -> None:
        """Restore removed_remote = 0 when a previously removed item reappears in the remote."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE items SET removed_remote = 0 WHERE id = ?;",
                (item_id,),
            )

    def reset_item_to_pending(self, item_id: int) -> None:
        """Reset an item whose local file is missing back to pending status."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE items SET status = 'pending', file_path = NULL WHERE id = ?;",
                (item_id,),
            )

    def update_item_position(self, item_id: int, position: int) -> None:
        """Update an item's position in the playlist."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE items SET position = ? WHERE id = ?;",
                (position, item_id),
            )

    # -------------------------------------------------------------------------
    # Settings CRUD
    # -------------------------------------------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?;", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
                (key, value),
            )

    # -------------------------------------------------------------------------
    # Deserializers
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_dt(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None

    @classmethod
    def _row_to_source(cls, row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            id=row["id"],
            kind=SourceKind(row["kind"]),
            url=row["url"],
            title=row["title"],
            cover_url=row["cover_url"],
            folder_name=row["folder_name"],
            status=SourceStatus(row["status"]),
            last_sync_at=cls._parse_dt(row["last_sync_at"]),
            last_error_code=row["last_error_code"],
            last_error_message=row["last_error_message"],
            last_known_count=row["last_known_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @classmethod
    def _row_to_item(cls, row: sqlite3.Row) -> ItemRecord:
        row_keys = row.keys()
        return ItemRecord(
            id=row["id"],
            source_id=row["source_id"],
            external_id=row["external_id"],
            title=row["title"],
            position=row["position"],
            published_at=cls._parse_dt(row["published_at"]),
            status=ItemStatus(row["status"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
            attempts=row["attempts"],
            file_path=row["file_path"],
            downloaded_at=cls._parse_dt(row["downloaded_at"]),
            removed_remote=bool(row["removed_remote"]),
            artist=row["artist"] if "artist" in row_keys else None,
        )
