"""Unified Composite Source Adapter routing between YouTube and RSS Podcasts (RF-1, RF-13, RF-14)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from playlist_sync.adapters.itunes_search import search_itunes_podcasts
from playlist_sync.adapters.rss_source import RssSource
from playlist_sync.adapters.ytdlp_source import ALLOWED_YOUTUBE_DOMAINS, YtDlpSource
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    DownloadedFile,
    Progress,
    RemoteItem,
    Source,
    SourceInfo,
    SourceKind,
    SourceRecord,
)

logger = logging.getLogger(__name__)


def is_youtube_url(url: str) -> bool:
    """Return True if the URL belongs to a YouTube domain."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_YOUTUBE_DOMAINS)
    except Exception:
        return False


class CompositeSource(Source):
    """Router adapter delegating to YtDlpSource or RssSource depending on the source type."""

    def __init__(
        self,
        yt_source: Source | None = None,
        rss_source: Source | None = None,
        rate_limit_bytes: int | None = None,
        sleep_interval: float | None = 2.0,
        sleep_interval_requests: float | None = 1.0,
    ) -> None:
        self.yt_source = yt_source or YtDlpSource(
            rate_limit_bytes=rate_limit_bytes,
            sleep_interval=sleep_interval,
            sleep_interval_requests=sleep_interval_requests,
        )
        self.rss_source = rss_source or RssSource()

    def inspect(self, url: str) -> SourceInfo:
        """Inspect a URL (or podcast search query) and return source info."""
        clean_input = url.strip()

        # 1. Direct YouTube URL
        if is_youtube_url(clean_input):
            return self.yt_source.inspect(clean_input)

        # 2. Direct HTTP/HTTPS link (RSS feed or direct podcast)
        if clean_input.startswith(("http://", "https://")):
            return self.rss_source.inspect(clean_input)

        # 3. Not a URL: treat as a podcast name search via iTunes Search API
        search_results = search_itunes_podcasts(clean_input, limit=1)
        if not search_results:
            raise AppError(
                ErrorCode.SOURCE_NOT_FOUND,
                user_message=f"No se encontró ningún podcast con el nombre '{clean_input}'.",
                technical_detail=f"iTunes search returned 0 results for '{clean_input}'",
            )

        top_match = search_results[0]
        logger.info("Resolved podcast query '%s' to feed URL: %s", clean_input, top_match.feed_url)
        return self.rss_source.inspect(top_match.feed_url)

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        """Fetch items using the appropriate adapter based on source kind."""
        if source.kind in (SourceKind.YT_PLAYLIST, SourceKind.YT_PODCAST):
            return self.yt_source.list_items(source)
        return self.rss_source.list_items(source)

    def download(
        self,
        item: RemoteItem,
        dest_dir: Path,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> DownloadedFile:
        """Download an item using the appropriate adapter."""
        if is_youtube_url(item.url):
            return self.yt_source.download(item, dest_dir, on_progress)
        return self.rss_source.download(item, dest_dir, on_progress)
