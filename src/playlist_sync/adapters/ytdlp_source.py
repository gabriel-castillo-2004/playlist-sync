"""yt-dlp adapter for YouTube and YouTube Music playlists (Section 5.2)."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp  # type: ignore[import-untyped]

from playlist_sync.adapters.repo import sanitize_filename
from playlist_sync.core.errors import (
    AppError,
    ErrorCode,
    classify_ytdlp_error,
)
from playlist_sync.core.models import (
    DownloadedFile,
    Progress,
    RemoteItem,
    SourceInfo,
    SourceKind,
    SourceRecord,
)

logger = logging.getLogger(__name__)

ALLOWED_YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def validate_youtube_url(url: str) -> None:
    """Validate that the given URL belongs to YouTube or YouTube Music."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise AppError(
                ErrorCode.INVALID_URL,
                technical_detail=f"Invalid scheme: {parsed.scheme}",
            )
        hostname = (parsed.hostname or "").lower()
        if not any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_YOUTUBE_DOMAINS):
            raise AppError(
                ErrorCode.INVALID_URL,
                technical_detail=f"Host '{hostname}' is not a valid YouTube domain.",
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(ErrorCode.INVALID_URL, technical_detail=str(exc)) from exc


def find_ffmpeg_location() -> str | None:
    """Find directory containing ffmpeg/ffprobe executable if not standard in PATH."""
    path = shutil.which("ffmpeg")
    if path:
        return str(Path(path).parent)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_candidates = list(
            Path(local_app_data).glob(
                "Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg*/bin/ffmpeg.exe"
            )
        )
        if winget_candidates:
            return str(winget_candidates[0].parent)
    return None


class YtDlpSource:
    """Source adapter backed by yt-dlp embedded API."""

    def __init__(self, rate_limit_bytes: int | None = None) -> None:
        self.rate_limit_bytes = rate_limit_bytes

    def inspect(self, url: str) -> SourceInfo:
        """Inspect a playlist URL without downloading files."""
        validate_youtube_url(url)

        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise classify_ytdlp_error(exc) from exc

        if not info:
            raise AppError(
                ErrorCode.SOURCE_NOT_FOUND,
                technical_detail=f"yt-dlp returned no info for {url}",
            )

        title = info.get("title") or "YouTube Playlist"
        # Determine thumbnail / cover
        cover_url = info.get("thumbnail")
        if not cover_url and info.get("thumbnails"):
            cover_url = info["thumbnails"][-1].get("url")

        entries = info.get("entries")
        item_count = len(list(entries)) if entries is not None else None

        return SourceInfo(
            url=url,
            kind=SourceKind.YT_PLAYLIST,
            title=title,
            cover_url=cover_url,
            item_count=item_count,
        )

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        """Fetch remote entries for a source without downloading."""
        validate_youtube_url(source.url)

        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,  # Keep going past individual removed/private items
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source.url, download=False)
        except Exception as exc:
            raise classify_ytdlp_error(exc) from exc

        if not info or "entries" not in info:
            return []

        remote_items: list[RemoteItem] = []
        position = 1

        for entry in info["entries"]:
            if not entry:
                continue
            video_id = entry.get("id")
            if not video_id:
                continue

            raw_title = entry.get("title") or f"Track {video_id}"
            # Filter unavailable stubs
            if raw_title in ("[Private video]", "[Deleted video]"):
                continue

            upload_date = entry.get("upload_date")
            pub_date: datetime | None = None
            if upload_date and len(upload_date) == 8:
                try:
                    pub_date = datetime.strptime(upload_date, "%Y%m%d")
                except ValueError:
                    pass

            item_url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            if not item_url.startswith("http"):
                item_url = f"https://www.youtube.com/watch?v={video_id}"

            remote_items.append(
                RemoteItem(
                    external_id=str(video_id),
                    title=raw_title,
                    position=position,
                    url=item_url,
                    published_at=pub_date,
                    duration_seconds=entry.get("duration"),
                    thumbnail_url=entry.get("thumbnail"),
                )
            )
            position += 1

        return remote_items

    def download(
        self,
        item: RemoteItem,
        dest_dir: Path,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> DownloadedFile:
        """Download an item and extract audio as MP3."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        sanitized_title = sanitize_filename(item.title)
        output_template = str(dest_dir / f"{sanitized_title} [{item.external_id}].%(ext)s")
        expected_mp3 = dest_dir / f"{sanitized_title} [{item.external_id}].mp3"

        def _hook(d: dict[str, object]) -> None:
            if not on_progress:
                return
            status = str(d.get("status", "downloading"))
            raw_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            total = int(raw_total) if isinstance(raw_total, (int, float, str)) else 0
            raw_dl = d.get("downloaded_bytes") or 0
            downloaded = int(raw_dl) if isinstance(raw_dl, (int, float, str)) else 0
            percent = (downloaded / total * 100) if total > 0 else 0.0
            raw_speed = d.get("speed")
            speed = float(raw_speed) if isinstance(raw_speed, (int, float, str)) else None
            raw_eta = d.get("eta")
            eta = int(raw_eta) if isinstance(raw_eta, (int, float, str)) else None

            on_progress(
                Progress(
                    status=status,
                    current=downloaded,
                    total=total,
                    percentage=percent,
                    speed_bytes_per_sec=speed,
                    eta_seconds=eta,
                    current_item_title=item.title,
                )
            )

        ydl_opts: dict[str, object] = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_hook],
            "retries": 3,
        }

        ffmpeg_dir = find_ffmpeg_location()
        if ffmpeg_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_dir

        if self.rate_limit_bytes:
            ydl_opts["ratelimit"] = self.rate_limit_bytes

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([item.url])
        except Exception as exc:
            raise classify_ytdlp_error(exc) from exc

        if not expected_mp3.exists():
            # In case title was slightly altered by yt-dlp sanitize, search matching external_id
            candidates = list(dest_dir.glob(f"*[{item.external_id}].mp3"))
            if candidates:
                return DownloadedFile(
                    file_path=candidates[0],
                    external_id=item.external_id,
                    title=item.title,
                    duration_seconds=item.duration_seconds,
                )
            raise AppError(
                ErrorCode.UNKNOWN,
                technical_detail=f"Expected output file not found: {expected_mp3}",
            )

        return DownloadedFile(
            file_path=expected_mp3,
            external_id=item.external_id,
            title=item.title,
            duration_seconds=item.duration_seconds,
        )
