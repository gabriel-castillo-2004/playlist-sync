"""Unit tests for SQLite repository and data persistence."""

from pathlib import Path

from playlist_sync.adapters.repo import SQLiteRepo, sanitize_filename
from playlist_sync.core.models import ItemStatus, SourceKind, SourceStatus


def test_sanitize_filename() -> None:
    assert sanitize_filename('A/B\\C:D*E?F"G<H>I|J') == "A B C D E F G H I J"
    assert sanitize_filename("  Leading and trailing.  ") == "Leading and trailing"
    assert sanitize_filename("...") == "untitled"
    assert sanitize_filename("Song Name 😔👍") == "Song Name 😔👍"


def test_repo_init_and_source_crud(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    repo = SQLiteRepo(db_file)

    # Add source
    src = repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PL123",
        title="My Cool Playlist",
        cover_url="https://img.youtube.com/thumb.jpg",
    )
    assert src.id == 1
    assert src.folder_name == "My Cool Playlist"
    assert src.status == SourceStatus.IDLE

    # Case-insensitive collision detection for folder_name
    src2 = repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PL456",
        title="my cool playlist",
    )
    assert src2.id == 2
    assert src2.folder_name == "my cool playlist (1)"

    # Get by ID and URL
    assert repo.get_source(1) is not None
    assert repo.get_source_by_url("https://youtube.com/playlist?list=PL123") is not None
    assert repo.get_source(999) is None

    # List sources
    all_sources = repo.list_sources()
    assert len(all_sources) == 2

    # Update status
    repo.update_source_status(
        source_id=1,
        status=SourceStatus.SYNCING,
        last_known_count=15,
    )
    updated = repo.get_source(1)
    assert updated is not None
    assert updated.status == SourceStatus.SYNCING
    assert updated.last_known_count == 15
    assert updated.last_sync_at is not None


def test_repo_items_crud(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    repo = SQLiteRepo(db_file)
    src = repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PL123",
        title="Playlist 1",
    )

    # Upsert item
    item1 = repo.upsert_item(
        source_id=src.id,
        external_id="vid_1",
        title="Song One",
        position=1,
    )
    assert item1.status == ItemStatus.PENDING
    assert item1.attempts == 0
    assert not item1.removed_remote

    # Update status to downloaded
    repo.update_item_status(
        item_id=item1.id,
        status=ItemStatus.DOWNLOADED,
        file_path="music_root/Song One [vid_1].mp3",
        increment_attempts=True,
    )
    item1_updated = repo.get_item(item1.id)
    assert item1_updated is not None
    assert item1_updated.status == ItemStatus.DOWNLOADED
    assert item1_updated.attempts == 1
    assert item1_updated.file_path == "music_root/Song One [vid_1].mp3"
    assert item1_updated.downloaded_at is not None

    # Upsert same item with updated title/position (does not overwrite downloaded status)
    item1_reupsert = repo.upsert_item(
        source_id=src.id,
        external_id="vid_1",
        title="Song One (Remastered)",
        position=5,
    )
    assert item1_reupsert.title == "Song One (Remastered)"
    assert item1_reupsert.position == 5
    assert item1_reupsert.status == ItemStatus.DOWNLOADED

    # Mark removed remote
    repo.mark_item_removed_remote(item1.id)
    assert repo.get_item(item1.id).removed_remote is True


def test_repo_settings(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    repo = SQLiteRepo(db_file)

    assert repo.get_setting("non_existent", "default_val") == "default_val"
    repo.set_setting("theme", "dark")
    assert repo.get_setting("theme") == "dark"
    repo.set_setting("theme", "light")
    assert repo.get_setting("theme") == "light"
