"""Core domain models and interfaces for Playlist Sync."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class SourceKind(StrEnum):
    YT_PLAYLIST = "yt_playlist"
    YT_PODCAST = "yt_podcast"
    RSS_PODCAST = "rss_podcast"


class SourceStatus(StrEnum):
    IDLE = "idle"
    SYNCING = "syncing"
    ERROR = "error"


class ItemStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"


@dataclass(frozen=True)
class SourceInfo:
    """Information gathered about a source without downloading content."""

    url: str
    kind: SourceKind
    title: str
    cover_url: str | None = None
    item_count: int | None = None


@dataclass(frozen=True)
class RemoteItem:
    """An individual item as reported by the remote source."""

    external_id: str
    title: str
    position: int
    url: str
    published_at: datetime | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


@dataclass(frozen=True)
class DownloadedFile:
    """A successfully downloaded file on disk."""

    file_path: Path
    external_id: str
    title: str
    duration_seconds: int | None = None


@dataclass
class Progress:
    """Real-time progress notification during download."""

    status: str
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    speed_bytes_per_sec: float | None = None
    eta_seconds: int | None = None
    current_item_title: str | None = None


@dataclass
class SourceRecord:
    """Database record of a tracked source."""

    id: int
    kind: SourceKind
    url: str
    title: str
    cover_url: str | None
    folder_name: str
    status: SourceStatus
    last_sync_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    last_known_count: int
    created_at: datetime


@dataclass
class ItemRecord:
    """Database record of a playlist item / track."""

    id: int
    source_id: int
    external_id: str
    title: str
    position: int
    published_at: datetime | None
    status: ItemStatus
    error_code: str | None
    error_message: str | None
    attempts: int
    file_path: str | None
    downloaded_at: datetime | None
    removed_remote: bool = False


@dataclass
class SyncPlan:
    """Calculated plan for an incremental synchronization."""

    items_to_download: list[RemoteItem]
    items_to_mark_removed: list[ItemRecord]
    items_to_update_position: list[tuple[ItemRecord, int]]
    total_remote: int


@dataclass
class SyncResult:
    """Summary of a finished synchronization run."""

    source_id: int
    total_remote: int
    downloaded_count: int
    skipped_count: int
    failed_count: int
    removed_count: int
    error: str | None = None
    failed_items: list[tuple[str, str]] = field(default_factory=list)


class Source(Protocol):
    """External source adapter contract (Section 5.2)."""

    def inspect(self, url: str) -> SourceInfo:
        """Inspect source without downloading to retrieve title, cover and kind."""
        ...

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        """List all items currently present in the remote source."""
        ...

    def download(
        self,
        item: RemoteItem,
        dest_dir: Path,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> DownloadedFile:
        """Download an item to dest_dir as MP3."""
        ...


class Library(Protocol):
    """Local library writer and organizer contract (Section 5.2)."""

    def finalize_item(
        self,
        source: SourceRecord,
        item: ItemRecord,
        file: DownloadedFile,
        total_items: int = 1,
    ) -> Path:
        """Tag MP3 with ID3 metadata and embedded cover art."""
        ...

    def rebuild_playlist_file(
        self,
        source: SourceRecord,
        items: list[ItemRecord],
    ) -> Path:
        """Regenerate UTF-8 relative .m3u8 playlist file in the source directory."""
        ...
