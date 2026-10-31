"""RSS Podcast Source Adapter (RF-13).

Fetches podcast metadata and episodes directly from RSS XML feeds and streams audio enclosures.
"""

from __future__ import annotations

import email.utils
import hashlib
import logging
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from playlist_sync.adapters.repo import sanitize_filename
from playlist_sync.adapters.ytdlp_source import find_ffmpeg_location
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

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def parse_rfc822_date(date_str: str | None) -> datetime | None:
    """Parse RFC 2822 / 822 pubDate string to a UTC datetime."""
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def parse_duration_seconds(duration_str: str | None) -> int | None:
    """Parse itunes:duration into total seconds."""
    if not duration_str:
        return None
    cleaned = duration_str.strip()
    try:
        if ":" in cleaned:
            parts = [int(p) for p in cleaned.split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
        return int(float(cleaned))
    except Exception:
        return None


def extract_cover_url(channel_elem: ET.Element) -> str | None:
    """Extract cover image URL from RSS channel (itunes:image or standard image)."""
    # 1. itunes:image
    itunes_img = channel_elem.find("itunes:image", NS)
    if itunes_img is not None:
        href = itunes_img.get("href") or itunes_img.get("url")
        if href:
            return href.strip()

    # 2. standard <image><url>
    img_elem = channel_elem.find("image")
    if img_elem is not None:
        url_elem = img_elem.find("url")
        if url_elem is not None and url_elem.text:
            return url_elem.text.strip()

    # 3. Fallback scan by local tag
    for child in channel_elem:
        tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag_name.lower() in ("image", "cover"):
            href = child.get("href") or child.get("url")
            if href:
                return href.strip()
            url_node = child.find("url")
            if url_node is not None and url_node.text:
                return url_node.text.strip()

    return None


NON_MP3_EXTENSIONS = (
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".webm",
    ".wav",
    ".flac",
    ".mp4",
)

NON_MP3_MIME_PREFIXES = (
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "application/ogg",
    "audio/opus",
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "video/mp4",
)


def _is_mp3_magic(header: bytes) -> bool:
    """Return True if header bytes match an ID3v2 tag or MPEG audio frame sync."""
    if len(header) < 4:
        return False
    if header.startswith(b"ID3"):
        return True
    if header.startswith((b"OggS", b"fLaC", b"RIFF", b"\x1aE\xdf\xa3")) or header[4:8] == b"ftyp":
        return False
    return header[0] == 0xFF and (header[1] & 0xE0) == 0xE0


def _needs_mp3_conversion(url: str, content_type: str | None, header: bytes) -> bool:
    """Detect whether a downloaded enclosure is non-MP3 by Content-Type, URL extension, or magic bytes."""
    if not _is_mp3_magic(header):
        return True
    if content_type:
        ct_lower = content_type.split(";")[0].strip().lower()
        if ct_lower in NON_MP3_MIME_PREFIXES:
            return True
    path_lower = urlparse(url).path.lower()
    return path_lower.endswith(NON_MP3_EXTENSIONS)


def _cleanup_part_file(part_path: Path, dest_dir: Path) -> None:
    """Safely remove a temporary .part file inside dest_dir without ever touching .mp3 files."""
    resolved_dir = dest_dir.resolve()
    resolved_part = part_path.resolve()
    if resolved_part.parent != resolved_dir or not resolved_part.name.endswith(".part"):
        raise ValueError(f"Refusing to delete non-.part file: {resolved_part}")
    if resolved_part.exists():
        resolved_part.unlink()


def _convert_part_to_mp3(source_part: Path, target_part: Path) -> None:
    """Convert a non-MP3 audio file to MP3 using ffmpeg with shell=False."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        ffmpeg_dir = find_ffmpeg_location()
        if ffmpeg_dir:
            candidate = Path(ffmpeg_dir) / ("ffmpeg.exe" if Path(ffmpeg_dir).drive else "ffmpeg")
            if candidate.exists():
                ffmpeg_bin = str(candidate)
    if not ffmpeg_bin:
        raise AppError(
            ErrorCode.TOOL_MISSING,
            user_message="Falta un programa necesario (ffmpeg). Ejecuta la revisión del sistema.",
            technical_detail="ffmpeg binary not found for RSS audio conversion.",
        )

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(source_part),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        "-f",
        "mp3",
        str(target_part),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if proc.returncode != 0 or not target_part.exists() or target_part.stat().st_size == 0:
        raise AppError(
            ErrorCode.UNKNOWN,
            user_message="No se pudo convertir el audio del episodio a MP3.",
            technical_detail=f"ffmpeg conversion failed (exit {proc.returncode}): {proc.stderr[-300:]}",
        )


class RssSource(Source):
    """Direct RSS podcast parser and audio downloader (RF-13)."""

    def __init__(self, client: httpx.Client | None = None, timeout: float = 20.0) -> None:
        self._custom_client = client
        self.timeout = timeout

    def _fetch_xml(self, url: str) -> bytes:
        """Fetch XML content via HTTP with strict error classification."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise AppError(
                ErrorCode.INVALID_URL,
                user_message="Ese link no parece de YouTube ni de un podcast.",
                technical_detail=f"Invalid scheme for RSS feed: {parsed.scheme}",
            )

        client = self._custom_client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "PlaylistSync/0.1.0 (Podcast Downloader)"},
        )
        owns_client = self._custom_client is None

        try:
            resp = client.get(url)
            if resp.status_code == 404:
                raise AppError(
                    ErrorCode.SOURCE_NOT_FOUND,
                    user_message="No encontré esa playlist o podcast. Revisa que el link esté completo.",
                    technical_detail=f"HTTP 404 for {url}",
                )
            if resp.status_code == 403:
                raise AppError(
                    ErrorCode.PRIVATE_SOURCE,
                    user_message="Este feed es privado o requiere autenticación.",
                    technical_detail=f"HTTP 403 for {url}",
                )
            resp.raise_for_status()
            return resp.content
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AppError(
                ErrorCode.NETWORK,
                user_message="No hay conexión a internet o el servidor del podcast no responde.",
                technical_detail=f"Feed fetch network error: {exc}",
            ) from exc
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.UNKNOWN,
                technical_detail=f"Error fetching feed: {exc}",
            ) from exc
        finally:
            if owns_client:
                client.close()

    def _parse_root(self, xml_bytes: bytes) -> ET.Element:
        """Parse raw XML bytes safely into an ElementTree root."""
        try:
            return ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            raise AppError(
                ErrorCode.INVALID_URL,
                user_message="Ese link no parece de YouTube ni de un podcast válido.",
                technical_detail=f"XML ParseError: {exc}",
            ) from exc

    def inspect(self, url: str) -> SourceInfo:
        """Inspect a podcast RSS feed to extract title, cover and item count without downloading."""
        content = self._fetch_xml(url)
        root = self._parse_root(content)

        channel = root.find("channel")
        if channel is None:
            # Fallback for feeds without explicit channel tag
            channel = root

        title_elem = channel.find("title")
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Podcast"

        cover_url = extract_cover_url(channel)
        items = channel.findall("item")

        return SourceInfo(
            url=url,
            kind=SourceKind.RSS_PODCAST,
            title=title,
            cover_url=cover_url,
            item_count=len(items),
        )

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        """List all audio episodes in the podcast feed."""
        content = self._fetch_xml(source.url)
        root = self._parse_root(content)

        channel = root.find("channel")
        if channel is None:
            channel = root

        channel_author = (
            channel.findtext("itunes:author", namespaces=NS)
            or channel.findtext("author")
            or channel.findtext("managingEditor")
        )
        items_elems = channel.findall("item")
        remote_items: list[RemoteItem] = []

        for idx, item in enumerate(items_elems, start=1):
            title_elem = item.find("title")
            title = (
                title_elem.text.strip()
                if title_elem is not None and title_elem.text
                else f"Episodio {idx}"
            )
            raw_author = (
                item.findtext("itunes:author", namespaces=NS)
                or item.findtext("author")
                or channel_author
            )
            artist = raw_author.strip() if raw_author and raw_author.strip() else None

            # Find audio enclosure
            enc_url: str | None = None
            enc = item.find("enclosure")
            if enc is not None:
                enc_url = enc.get("url")

            # Fallback to media:content
            if not enc_url:
                media_elem = item.find("media:content", NS)
                if media_elem is not None:
                    enc_url = media_elem.get("url")

            if not enc_url:
                continue

            # Deterministic, unique external_id
            guid_elem = item.find("guid")
            guid_text = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None

            if guid_text:
                # Sanitize or hash long/special guid
                clean_guid = "".join(c for c in guid_text if c.isalnum() or c in ("-", "_"))
                external_id = (
                    clean_guid[:64]
                    if len(clean_guid) >= 4
                    else hashlib.sha1(guid_text.encode()).hexdigest()[:16]
                )
            else:
                external_id = hashlib.sha1(enc_url.encode()).hexdigest()[:16]

            pub_date = parse_rfc822_date(item.findtext("pubDate"))
            duration = parse_duration_seconds(item.findtext("itunes:duration", namespaces=NS))

            remote_items.append(
                RemoteItem(
                    external_id=external_id,
                    title=title,
                    position=idx,
                    url=enc_url.strip(),
                    published_at=pub_date,
                    duration_seconds=duration,
                    artist=artist,
                )
            )

        return remote_items

    def download(
        self,
        item: RemoteItem,
        dest_dir: Path,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> DownloadedFile:
        """Download an episode's audio enclosure directly to disk with live progress."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        clean_title = sanitize_filename(item.title)
        final_filename = f"{clean_title} [{item.external_id}].mp3"
        final_path = dest_dir / final_filename
        temp_path = dest_dir / f"{final_filename}.part"

        # Idempotence: never overwrite an existing complete MP3 file
        if final_path.is_file() and final_path.stat().st_size > 0:
            if on_progress:
                on_progress(
                    Progress(status="finished", percentage=100.0, current_item_title=item.title)
                )
            return DownloadedFile(
                file_path=final_path,
                external_id=item.external_id,
                title=item.title,
                duration_seconds=item.duration_seconds,
            )

        client = self._custom_client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "PlaylistSync/0.1.0 (Podcast Downloader)"},
        )
        owns_client = self._custom_client is None

        try:
            offset = temp_path.stat().st_size if temp_path.is_file() else 0
            content_type: str | None = None
            start_time = time.monotonic()

            for attempt in range(2):
                req_headers: dict[str, str] = {}
                if offset > 0:
                    req_headers["Range"] = f"bytes={offset}-"

                supports_range = False
                with client.stream("GET", item.url, headers=req_headers) as resp:
                    if resp.status_code == 404:
                        raise AppError(
                            ErrorCode.ITEM_UNAVAILABLE,
                            user_message="Este episodio ya no está disponible en el servidor.",
                            technical_detail=f"HTTP 404 for enclosure {item.url}",
                        )
                    resp.raise_for_status()

                    content_type = resp.headers.get("content-type") or content_type
                    accept_ranges = resp.headers.get("accept-ranges", "").lower()
                    raw_cl = int(resp.headers.get("content-length", 0))

                    if offset > 0 and resp.status_code == 206:
                        mode = "ab"
                        total_bytes = (offset + raw_cl) if raw_cl > 0 else 0
                        downloaded_bytes = offset
                        supports_range = True
                    else:
                        # Server does not support Range or initial request from byte 0
                        offset = 0
                        mode = "wb"
                        total_bytes = raw_cl
                        downloaded_bytes = 0
                        supports_range = accept_ranges == "bytes"

                    with temp_path.open(mode) as out_file:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            if not chunk:
                                continue
                            out_file.write(chunk)
                            downloaded_bytes += len(chunk)

                            if on_progress:
                                elapsed = time.monotonic() - start_time
                                speed = downloaded_bytes / elapsed if elapsed > 0 else None
                                percent = (
                                    (downloaded_bytes / total_bytes * 100.0)
                                    if total_bytes > 0
                                    else 0.0
                                )
                                on_progress(
                                    Progress(
                                        status="downloading",
                                        current=downloaded_bytes,
                                        total=total_bytes,
                                        percentage=round(percent, 1),
                                        speed_bytes_per_sec=speed,
                                        current_item_title=item.title,
                                    )
                                )

                # Verify downloaded size matches Content-Length (H-07)
                if total_bytes > 0:
                    if downloaded_bytes == total_bytes:
                        break
                    if attempt == 0 and supports_range and downloaded_bytes > offset:
                        offset = downloaded_bytes
                        continue
                    raise AppError(
                        ErrorCode.NETWORK,
                        user_message="La descarga del episodio quedó incompleta por un corte de red.",
                        technical_detail=(
                            f"Incomplete enclosure download for {item.url}: "
                            f"received {downloaded_bytes} of {total_bytes} bytes."
                        ),
                    )
                else:
                    if downloaded_bytes > 0:
                        break
                    raise AppError(
                        ErrorCode.NETWORK,
                        user_message="El servidor devolvió un archivo de audio vacío.",
                        technical_detail=f"Empty enclosure response (0 bytes) for {item.url}",
                    )

            # Check if conversion to MP3 is needed (H-06)
            if temp_path.exists():
                with temp_path.open("rb") as fh:
                    header_bytes = fh.read(16)
                if _needs_mp3_conversion(item.url, content_type, header_bytes):
                    converted_part = dest_dir / f"{final_filename}.conv.part"
                    try:
                        _convert_part_to_mp3(temp_path, converted_part)
                        converted_part.replace(final_path)
                    finally:
                        _cleanup_part_file(converted_part, dest_dir)
                        _cleanup_part_file(temp_path, dest_dir)
                else:
                    temp_path.replace(final_path)

            if on_progress:
                on_progress(
                    Progress(status="finished", percentage=100.0, current_item_title=item.title)
                )

            return DownloadedFile(
                file_path=final_path,
                external_id=item.external_id,
                title=item.title,
                duration_seconds=item.duration_seconds,
            )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            _cleanup_part_file(temp_path, dest_dir)
            raise AppError(
                ErrorCode.NETWORK,
                user_message="No hay conexión a internet o falló la descarga del episodio.",
                technical_detail=f"Download network error: {exc}",
            ) from exc
        except AppError:
            _cleanup_part_file(temp_path, dest_dir)
            raise
        except Exception as exc:
            _cleanup_part_file(temp_path, dest_dir)
            raise AppError(
                ErrorCode.UNKNOWN,
                technical_detail=f"Unexpected download failure: {exc}",
            ) from exc
        finally:
            if owns_client:
                client.close()
