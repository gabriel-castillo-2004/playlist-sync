"""Library organizer, ID3 tagger and .m3u8 playlist generator (Section 6.2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TRCK,
    ID3NoHeaderError,
)

from playlist_sync.adapters.repo import sanitize_filename
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    DownloadedFile,
    ItemRecord,
    ItemStatus,
    SourceKind,
    SourceRecord,
)

logger = logging.getLogger(__name__)


def parse_artist_and_title(raw_title: str, fallback_artist: str) -> tuple[str, str]:
    """Extract (artist, title) from common formats like 'Artist - Song Title'."""
    for separator in (" - ", " — ", " | "):
        if separator in raw_title:
            parts = raw_title.split(separator, 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            if artist and title:
                return artist, title
    return fallback_artist, raw_title.strip()


def _normalize_pub_date(dt: datetime | None) -> datetime:
    """Normalize published_at to a timezone-naive UTC datetime for homogeneous sorting."""
    if dt is None:
        return datetime.min
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def download_cover_image(url: str, dest_path: Path) -> bool:
    """Download cover image from URL and save to dest_path."""
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200 and len(resp.content) > 0:
                dest_path.write_bytes(resp.content)
                return True
    except Exception as exc:
        logger.warning("Could not download cover image from %s: %s", url, exc)
    return False


def apply_id3_tags(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    position: int,
    total_tracks: int,
    genre: str | None = None,
    published_date: str | None = None,
    cover_bytes: bytes | None = None,
) -> None:
    """Write standard ID3v2.3 tags and embedded front cover to an MP3 file."""
    try:
        tags = ID3(str(file_path))
    except ID3NoHeaderError:
        tags = ID3()

    tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
    tags.setall("TALB", [TALB(encoding=3, text=album)])
    tags.setall("TRCK", [TRCK(encoding=3, text=f"{position}/{total_tracks}")])

    if genre:
        tags.setall("TCON", [TCON(encoding=3, text=genre)])
    if published_date:
        tags.setall("TDRC", [TDRC(encoding=3, text=published_date)])

    if cover_bytes:
        # Determine MIME type
        mime = "image/png" if cover_bytes.startswith(b"\x89PNG") else "image/jpeg"
        tags.setall(
            "APIC",
            [
                APIC(
                    encoding=3,
                    mime=mime,
                    type=3,  # Front cover
                    desc="Cover",
                    data=cover_bytes,
                )
            ],
        )

    tags.save(str(file_path), v2_version=3)


class LocalLibrary:
    """Manages files, tags, and .m3u8 playlist generation inside music_root."""

    def __init__(self, music_root: Path | str) -> None:
        self.music_root = Path(music_root).resolve()
        self.music_root.mkdir(parents=True, exist_ok=True)

    def get_source_dir(self, source: SourceRecord) -> Path:
        """Resolve and validate destination directory for a source within music_root."""
        folder_name = sanitize_filename(source.folder_name)
        target = (self.music_root / folder_name).resolve()
        # Path traversal security check
        if not target.is_relative_to(self.music_root):
            raise AppError(
                ErrorCode.UNKNOWN,
                technical_detail=f"Security violation: path traversal detected for {target}",
            )
        target.mkdir(parents=True, exist_ok=True)
        return target

    def ensure_source_cover(self, source: SourceRecord) -> Path | None:
        """Ensure cover.jpg exists in the source directory if a cover URL is known."""
        if not source.cover_url:
            return None
        source_dir = self.get_source_dir(source)
        cover_path = source_dir / "cover.jpg"
        if not cover_path.exists():
            download_cover_image(source.cover_url, cover_path)
        return cover_path if cover_path.exists() else None

    def finalize_item(
        self,
        source: SourceRecord,
        item: ItemRecord,
        file: DownloadedFile,
        total_items: int = 1,
    ) -> Path:
        """Embed ID3 tags and album art into the downloaded MP3 file."""
        if not file.file_path.exists():
            raise AppError(
                ErrorCode.UNKNOWN,
                technical_detail=f"Audio file does not exist: {file.file_path}",
            )

        self.get_source_dir(source)
        cover_path = self.ensure_source_cover(source)
        cover_bytes = cover_path.read_bytes() if cover_path and cover_path.exists() else None

        artist, song_title = parse_artist_and_title(item.title, fallback_artist=source.title)
        genre = (
            "Podcast" if source.kind in (SourceKind.YT_PODCAST, SourceKind.RSS_PODCAST) else None
        )
        date_str = item.published_at.strftime("%Y-%m-%d") if item.published_at else None

        apply_id3_tags(
            file_path=file.file_path,
            title=song_title,
            artist=artist,
            album=source.title,
            position=item.position,
            total_tracks=max(total_items, item.position),
            genre=genre,
            published_date=date_str,
            cover_bytes=cover_bytes,
        )

        return file.file_path

    def update_track_position_tag(
        self,
        file_path: Path,
        new_position: int,
        total_tracks: int,
    ) -> None:
        """Update only the TRCK tag on an existing MP3 when playlist order changes."""
        if not file_path.exists():
            return
        try:
            tags = ID3(str(file_path))
            tags.setall("TRCK", [TRCK(encoding=3, text=f"{new_position}/{total_tracks}")])
            tags.save(str(file_path), v2_version=3)
        except Exception as exc:
            logger.warning("Could not update TRCK tag on %s: %s", file_path, exc)

    def rebuild_playlist_file(
        self,
        source: SourceRecord,
        items: list[ItemRecord],
    ) -> Path:
        """Generate relative, UTF-8 encoded .m3u8 file for any music player.

        - Extended M3U format (#EXTM3U, #EXTINF).
        - Relative paths (only filename, no directory paths).
        - Idempotent and regenerable.
        - Excludes items without local files or marked as removed.
        """
        source_dir = self.get_source_dir(source)
        playlist_path = source_dir / f"{source.folder_name}.m3u8"

        # Filter items: only downloaded and whose files actually exist
        valid_items: list[tuple[ItemRecord, Path]] = []
        for it in items:
            if it.status == ItemStatus.DOWNLOADED and it.file_path and not it.removed_remote:
                f_path = Path(it.file_path)
                # In case relative or absolute, check if it exists
                actual_path = f_path if f_path.is_absolute() else (self.music_root / f_path)
                if not actual_path.exists():
                    actual_path = source_dir / f_path.name
                if actual_path.exists():
                    valid_items.append((it, actual_path))

        # Sort order: for podcasts, newest first (by published_at); for playlists, by position ASC
        if source.kind in (SourceKind.YT_PODCAST, SourceKind.RSS_PODCAST):
            valid_items.sort(
                key=lambda pair: (_normalize_pub_date(pair[0].published_at), pair[0].id),
                reverse=True,
            )
        else:
            valid_items.sort(key=lambda pair: pair[0].position)

        lines: list[str] = ["#EXTM3U"]
        for it, actual_path in valid_items:
            artist, title = parse_artist_and_title(it.title, fallback_artist=source.title)
            lines.append(f"#EXTINF:-1,{artist} - {title}")
            lines.append(actual_path.name)  # Strictly relative to source folder

        content = "\n".join(lines) + "\n"

        # Write UTF-8 without BOM
        playlist_path.write_text(content, encoding="utf-8")
        return playlist_path
