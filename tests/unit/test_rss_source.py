"""Unit tests for the RSS Source Adapter (RF-13)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from playlist_sync.adapters.rss_source import RssSource
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    Progress,
    RemoteItem,
    SourceKind,
    SourceRecord,
    SourceStatus,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_rss_inspect_valid_feed() -> None:
    xml_content = (FIXTURES_DIR / "valid_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    info = source.inspect("https://example.com/podcast.xml")
    assert info.title == "Charlas de Tecnología"
    assert info.kind == SourceKind.RSS_PODCAST
    assert info.cover_url == "https://example.com/podcast/cover.jpg"
    assert info.item_count == 2


def test_rss_list_items_valid_feed() -> None:
    xml_content = (FIXTURES_DIR / "valid_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    src_record = SourceRecord(
        id=1,
        kind=SourceKind.RSS_PODCAST,
        url="https://example.com/podcast.xml",
        title="Charlas de Tecnología",
        cover_url=None,
        folder_name="Charlas",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=None,  # type: ignore[arg-type]
    )

    items = source.list_items(src_record)
    assert len(items) == 2
    assert items[0].title == "Episodio 2: Agentes y Modelos de Lenguaje"
    assert items[0].external_id == "ep-002-agentes"
    assert items[0].url == "https://example.com/audio/ep2.mp3"
    assert items[0].published_at is not None
    assert items[0].duration_seconds == 1800
    assert items[0].artist == "María Ingeniera"

    assert items[1].title == "Episodio 1: Bienvenidos al podcast"
    assert items[1].duration_seconds == 1200
    assert items[1].artist == "María Ingeniera"


def test_rss_inspect_no_cover() -> None:
    xml_content = (FIXTURES_DIR / "no_cover_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    info = source.inspect("https://example.com/no-cover.xml")
    assert info.title == "Podcast Sin Portada"
    assert info.cover_url is None
    assert info.item_count == 1


def test_rss_list_items_weird_enclosures() -> None:
    xml_content = (FIXTURES_DIR / "weird_enclosure_podcast.xml").read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml_content)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    src_record = SourceRecord(
        id=2,
        kind=SourceKind.RSS_PODCAST,
        url="https://example.com/weird.xml",
        title="Weird",
        cover_url=None,
        folder_name="Weird",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=None,  # type: ignore[arg-type]
    )

    items = source.list_items(src_record)
    assert len(items) == 2
    assert "token=xyz123" in items[0].url
    assert "media_fallback.mp3" in items[1].url


def test_rss_download_enclosure(tmp_path: Path) -> None:
    audio_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90d" * 500

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=audio_bytes,
            headers={"Content-Length": str(len(audio_bytes))},
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    item = RemoteItem(
        external_id="ep123",
        title="Podcast Audio Ep 1",
        position=1,
        url="https://example.com/ep1.mp3",
    )

    progress_events: list[Progress] = []
    dest_dir = tmp_path / "episodes"

    downloaded = source.download(item, dest_dir, on_progress=progress_events.append)
    assert downloaded.file_path.exists()
    assert downloaded.file_path.name == "Podcast Audio Ep 1 [ep123].mp3"
    assert len(progress_events) >= 1
    assert progress_events[-1].percentage == 100.0

    # Idempotent second call: doesn't re-download
    progress_events.clear()
    downloaded2 = source.download(item, dest_dir, on_progress=progress_events.append)
    assert downloaded2.file_path == downloaded.file_path
    assert len(progress_events) == 1
    assert progress_events[0].status == "finished"


def test_rss_errors_invalid_feed() -> None:
    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"Not valid XML <<>>")

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    with pytest.raises(AppError) as exc:
        source.inspect("https://example.com/bad.xml")
    assert exc.value.code == ErrorCode.INVALID_URL


def test_rss_errors_http_404() -> None:
    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    with pytest.raises(AppError) as exc:
        source.inspect("https://example.com/notfound.xml")
    assert exc.value.code == ErrorCode.SOURCE_NOT_FOUND


@pytest.mark.parametrize(
    ("fixture_name", "content_type", "url_ext"),
    [
        ("sample_tone.m4a", "audio/mp4", ".m4a"),
        ("sample_tone.ogg", "audio/ogg", ".ogg"),
        ("sample_tone.ogg", "application/octet-stream", ".bin"),
    ],
)
def test_rss_download_converts_non_mp3_enclosures_to_mp3(
    tmp_path: Path, fixture_name: str, content_type: str, url_ext: str
) -> None:
    """H-06: Non-MP3 enclosures (.m4a, .ogg, magic header) must be converted to real MP3 via ffmpeg."""
    from mutagen.mp3 import MP3

    raw_bytes = (FIXTURES_DIR / fixture_name).read_bytes()

    def transport(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=raw_bytes,
            headers={
                "Content-Length": str(len(raw_bytes)),
                "Content-Type": content_type,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    item = RemoteItem(
        external_id=f"ep_{fixture_name}_{url_ext.strip('.')}",
        title=f"Episode {fixture_name}",
        position=1,
        url=f"https://example.com/audio/episode{url_ext}",
    )

    dest_dir = tmp_path / "podcast_out"
    downloaded = source.download(item, dest_dir)
    assert downloaded.file_path.exists()
    assert downloaded.file_path.suffix == ".mp3"

    out_bytes = downloaded.file_path.read_bytes()
    assert not out_bytes.startswith(b"OggS")
    assert b"ftyp" not in out_bytes[:16]

    # Verify mutagen MP3 parser recognizes it as a valid MPEG audio file
    mp3_info = MP3(str(downloaded.file_path))
    assert mp3_info.info.length > 0


def test_rss_download_truncated_stream_raises_and_cleans_part_without_touching_mp3(
    tmp_path: Path,
) -> None:
    """H-07: If downloaded_bytes < Content-Length, abort, clean .part, and never touch complete .mp3."""
    dest_dir = tmp_path / "episodes"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_mp3 = dest_dir / "Episodio Previo [ep0].mp3"
    existing_mp3.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90d" * 100)

    partial_payload = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90d" * 200

    def transport(req: httpx.Request) -> httpx.Response:
        # Advertises 20000 bytes but only delivers partial_payload
        return httpx.Response(
            200,
            content=partial_payload,
            headers={"Content-Length": "20000", "Content-Type": "audio/mpeg"},
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    item = RemoteItem(
        external_id="ep_trunc",
        title="Episodio Cortado",
        position=2,
        url="https://example.com/audio/ep_trunc.mp3",
    )

    with pytest.raises(AppError) as exc:
        source.download(item, dest_dir)
    assert exc.value.code == ErrorCode.NETWORK

    # Neither a truncated .mp3 nor an orphan .part may exist
    assert not (dest_dir / "Episodio Cortado [ep_trunc].mp3").exists()
    assert list(dest_dir.glob("*.part")) == []
    # Existing complete MP3 must remain intact
    assert existing_mp3.exists()


def test_rss_download_resumes_with_range_when_server_supports_206(tmp_path: Path) -> None:
    """H-07: If connection drops mid-download and server supports Range (206), resume and verify full size."""
    full_audio = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90d" * 600
    split_at = len(full_audio) // 2
    first_half = full_audio[:split_at]
    second_half = full_audio[split_at:]
    calls: list[str | None] = []

    def transport(req: httpx.Request) -> httpx.Response:
        range_hdr = req.headers.get("Range")
        calls.append(range_hdr)
        if range_hdr == f"bytes={split_at}-":
            return httpx.Response(
                206,
                content=second_half,
                headers={
                    "Content-Length": str(len(second_half)),
                    "Content-Range": f"bytes {split_at}-{len(full_audio) - 1}/{len(full_audio)}",
                    "Accept-Ranges": "bytes",
                    "Content-Type": "audio/mpeg",
                },
            )
        # First attempt cuts off after first_half despite advertising full Content-Length
        return httpx.Response(
            200,
            content=first_half,
            headers={
                "Content-Length": str(len(full_audio)),
                "Accept-Ranges": "bytes",
                "Content-Type": "audio/mpeg",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(transport))
    source = RssSource(client=client)

    item = RemoteItem(
        external_id="ep_resume",
        title="Episodio Reanudado",
        position=1,
        url="https://example.com/audio/ep_resume.mp3",
    )

    dest_dir = tmp_path / "episodes_resume"
    downloaded = source.download(item, dest_dir)
    assert downloaded.file_path.exists()
    assert downloaded.file_path.read_bytes() == full_audio
    assert calls == [None, f"bytes={split_at}-"]
    assert list(dest_dir.glob("*.part")) == []
