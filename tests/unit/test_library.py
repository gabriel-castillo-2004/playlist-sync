"""Unit and integration tests for LocalLibrary, ID3 tagging, and .m3u8 generation (Phase 2)."""

import ast
from datetime import datetime
from pathlib import Path

from mutagen.id3 import ID3

from playlist_sync.adapters.library import (
    LocalLibrary,
    apply_id3_tags,
    parse_artist_and_title,
)
from playlist_sync.core.models import (
    DownloadedFile,
    ItemRecord,
    ItemStatus,
    SourceKind,
    SourceRecord,
    SourceStatus,
)


def create_dummy_mp3(file_path: Path) -> Path:
    """Create a minimal valid MP3 frame file for testing mutagen."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"\xff\xfb\x90d" + b"\x00" * 300)
    return file_path


def test_parse_artist_and_title() -> None:
    assert parse_artist_and_title("Queen - Bohemian Rhapsody", "Default") == (
        "Queen",
        "Bohemian Rhapsody",
    )
    assert parse_artist_and_title("Pink Floyd — Time", "Default") == (
        "Pink Floyd",
        "Time",
    )
    assert parse_artist_and_title("Radiohead | Creep", "Default") == (
        "Radiohead",
        "Creep",
    )
    assert parse_artist_and_title("Stand By Me", "Ben E. King") == (
        "Ben E. King",
        "Stand By Me",
    )


def test_apply_and_read_id3_tags(tmp_path: Path) -> None:
    mp3_file = create_dummy_mp3(tmp_path / "song.mp3")
    fake_cover_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50  # Dummy JPEG

    apply_id3_tags(
        file_path=mp3_file,
        title="La Vida Es Un Carnaval",
        artist="Celia Cruz",
        album="Grandes Exitos",
        position=2,
        total_tracks=12,
        genre="Salsa",
        published_date="1998-05-12",
        cover_bytes=fake_cover_bytes,
    )

    # Read back with mutagen to verify tags
    tags = ID3(str(mp3_file))
    assert tags["TIT2"].text[0] == "La Vida Es Un Carnaval"
    assert tags["TPE1"].text[0] == "Celia Cruz"
    assert tags["TALB"].text[0] == "Grandes Exitos"
    assert tags["TRCK"].text[0] == "2/12"
    assert tags["TCON"].text[0] == "Salsa"
    assert str(tags["TDRC"].text[0]) == "1998-05-12"

    apic = tags.getall("APIC")[0]
    assert apic.mime == "image/jpeg"
    assert apic.type == 3  # Front cover
    assert apic.data == fake_cover_bytes


def test_rebuild_playlist_file_relative_and_utf8(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    lib = LocalLibrary(music_root)
    source = SourceRecord(
        id=1,
        kind=SourceKind.YT_PLAYLIST,
        url="http://pl",
        title="Salsitas 😔👍",
        cover_url=None,
        folder_name="Salsitas 😔👍",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=datetime.now(),
    )
    src_dir = lib.get_source_dir(source)

    # Create 2 audio files in the folder
    f1 = create_dummy_mp3(src_dir / "Joe Arroyo - Rebelion [vid1].mp3")
    f2 = create_dummy_mp3(src_dir / "Hector Lavoe - Periodico De Ayer [vid2].mp3")

    items = [
        ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Joe Arroyo - Rebelion",
            position=2,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path=str(f1),
            downloaded_at=datetime.now(),
        ),
        ItemRecord(
            id=2,
            source_id=1,
            external_id="vid2",
            title="Hector Lavoe - Periodico De Ayer",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path=str(f2),
            downloaded_at=datetime.now(),
        ),
        # Removed item: should not appear in .m3u8
        ItemRecord(
            id=3,
            source_id=1,
            external_id="vid3",
            title="Removed Track",
            position=3,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path=str(src_dir / "Removed Track [vid3].mp3"),
            downloaded_at=datetime.now(),
            removed_remote=True,
        ),
    ]

    m3u8_path = lib.rebuild_playlist_file(source, items)
    assert m3u8_path.exists()
    assert m3u8_path.name == "Salsitas 😔👍.m3u8"

    raw_bytes = m3u8_path.read_bytes()
    # RNF-6: UTF-8 without BOM
    assert not raw_bytes.startswith(b"\xef\xbb\xbf")

    content = raw_bytes.decode("utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    assert lines[0] == "#EXTM3U"
    # Position 1 first: Hector Lavoe
    assert "Periodico De Ayer" in lines[1]
    assert lines[2] == "Hector Lavoe - Periodico De Ayer [vid2].mp3"
    # Position 2 second: Joe Arroyo
    assert "Rebelion" in lines[3]
    assert lines[4] == "Joe Arroyo - Rebelion [vid1].mp3"
    # Removed track is excluded
    assert "Removed Track" not in content
    # All paths are relative (no path separators in filename lines)
    assert "/" not in lines[2] and "\\" not in lines[2]
    assert "/" not in lines[4] and "\\" not in lines[4]


def test_rebuild_playlist_idempotency(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    lib = LocalLibrary(music_root)
    source = SourceRecord(
        id=1,
        kind=SourceKind.YT_PLAYLIST,
        url="http://pl",
        title="Test Playlist",
        cover_url=None,
        folder_name="Test Playlist",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=datetime.now(),
    )
    src_dir = lib.get_source_dir(source)
    f1 = create_dummy_mp3(src_dir / "Song [id1].mp3")
    items = [
        ItemRecord(
            id=1,
            source_id=1,
            external_id="id1",
            title="Song",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path=str(f1),
            downloaded_at=datetime.now(),
        )
    ]

    p1 = lib.rebuild_playlist_file(source, items)
    bytes1 = p1.read_bytes()
    p2 = lib.rebuild_playlist_file(source, items)
    bytes2 = p2.read_bytes()
    assert bytes1 == bytes2


def test_reorder_playlist_updates_tags_without_renaming(tmp_path: Path) -> None:
    """Reordering updates TRCK tag on disk without renaming the file."""
    music_root = tmp_path / "music"
    lib = LocalLibrary(music_root)
    src_dir = music_root / "Reorder Test"
    f = create_dummy_mp3(src_dir / "Artist - Track [x1].mp3")

    apply_id3_tags(f, "Track", "Artist", "Album", position=1, total_tracks=5)
    tags_initial = ID3(str(f))
    assert tags_initial["TRCK"].text[0] == "1/5"

    # Reorder to position 4
    lib.update_track_position_tag(f, new_position=4, total_tracks=5)
    assert f.exists()  # Filename unchanged
    tags_after = ID3(str(f))
    assert tags_after["TRCK"].text[0] == "4/5"


def test_finalize_item_flow(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    lib = LocalLibrary(music_root)
    source = SourceRecord(
        id=1,
        kind=SourceKind.YT_PODCAST,
        url="http://pod",
        title="My Podcast",
        cover_url=None,
        folder_name="My Podcast",
        status=SourceStatus.IDLE,
        last_sync_at=None,
        last_error_code=None,
        last_error_message=None,
        last_known_count=0,
        created_at=datetime.now(),
    )
    src_dir = lib.get_source_dir(source)
    audio_file = create_dummy_mp3(src_dir / "Episode 1 [ep1].mp3")

    item = ItemRecord(
        id=1,
        source_id=1,
        external_id="ep1",
        title="Episode 1: The Beginning",
        position=1,
        published_at=datetime(2025, 1, 1),
        status=ItemStatus.DOWNLOADING,
        error_code=None,
        error_message=None,
        attempts=1,
        file_path=str(audio_file),
        downloaded_at=None,
    )
    dl = DownloadedFile(file_path=audio_file, external_id="ep1", title=item.title)

    final_path = lib.finalize_item(source, item, dl, total_items=10)
    assert final_path == audio_file

    tags = ID3(str(final_path))
    assert tags["TALB"].text[0] == "My Podcast"
    assert tags["TCON"].text[0] == "Podcast"
    assert str(tags["TDRC"].text[0]) == "2025-01-01"


def test_architecture_no_audio_file_deletion() -> None:
    """Architectural test: Ensure NO code in src/playlist_sync deletes audio or playlist files (RF-12)."""
    src_dir = Path("src/playlist_sync")
    py_files = [p for p in src_dir.rglob("*.py") if p.name != "doctor.py"]
    assert len(py_files) > 0

    dangerous_calls: list[str] = []
    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Detect any .unlink(), os.remove(), or os.unlink() in the entire codebase
                if isinstance(func, ast.Attribute) and func.attr in ("unlink", "remove", "rmdir"):
                    src_line = py_file.read_text(encoding="utf-8").splitlines()[node.lineno - 1]
                    dangerous_calls.append(f"{py_file}:{node.lineno} -> {src_line.strip()}")

    assert not dangerous_calls, f"Dangerous deletion calls found: {dangerous_calls}"
