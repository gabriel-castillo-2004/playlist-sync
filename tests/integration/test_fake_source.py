"""Integration tests for synchronization workflow using FakeSource (no network)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    DownloadedFile,
    ItemStatus,
    Progress,
    RemoteItem,
    SourceInfo,
    SourceKind,
    SourceRecord,
    SourceStatus,
)
from playlist_sync.services.sync import add_source_service, sync_source_service


class FakeSource:
    """Simulated Source adapter for deterministic, offline testing."""

    def __init__(
        self,
        title: str = "Fake Playlist",
        items: list[RemoteItem] | None = None,
        is_private: bool = False,
        fail_downloads: set[str] | None = None,
    ) -> None:
        self.title = title
        self.items = items if items is not None else []
        self.is_private = is_private
        self.fail_downloads = fail_downloads or set()
        self.download_calls: list[str] = []

    def inspect(self, url: str) -> SourceInfo:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise AppError(ErrorCode.INVALID_URL, f"Invalid URL scheme: {url}")
        if self.is_private:
            raise AppError(ErrorCode.PRIVATE_SOURCE, technical_detail="Fake private playlist")
        return SourceInfo(
            url=url,
            kind=SourceKind.YT_PLAYLIST,
            title=self.title,
            cover_url="http://fake.url/cover.jpg",
            item_count=len(self.items),
        )

    def list_items(self, source: SourceRecord) -> list[RemoteItem]:
        if self.is_private:
            raise AppError(ErrorCode.PRIVATE_SOURCE, technical_detail="Fake private playlist")
        return list(self.items)

    def download(
        self,
        item: RemoteItem,
        dest_dir: Path,
        on_progress: Callable[[Progress], None] | None = None,
    ) -> DownloadedFile:
        self.download_calls.append(item.external_id)
        if item.external_id in self.fail_downloads:
            raise AppError(ErrorCode.NETWORK, "Simulated network failure")

        dest_dir.mkdir(parents=True, exist_ok=True)
        fake_file = dest_dir / f"{item.title} [{item.external_id}].mp3"
        fake_file.write_bytes(b"\xff\xfb\x90d" + b"\x00" * 200)

        if on_progress:
            on_progress(
                Progress(status="finished", percentage=100.0, current_item_title=item.title)
            )

        return DownloadedFile(
            file_path=fake_file,
            external_id=item.external_id,
            title=item.title,
        )


def test_full_sync_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "sync_test.sqlite3"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_path)

    # 1. Initial playlist with 2 items
    initial_items = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://v1"),
        RemoteItem(external_id="vid2", title="Song 2", position=2, url="http://v2"),
    ]
    fake = FakeSource(title="My Playlist", items=initial_items)

    # Add source
    source = add_source_service(repo, fake, "https://youtube.com/playlist?list=PLtest")
    assert source.id == 1
    assert source.title == "My Playlist"

    # First sync: downloads both items
    res1 = sync_source_service(
        repo=repo,
        source_adapter=fake,
        source_id=source.id,
        music_root=music_root,
    )
    assert res1.downloaded_count == 2
    assert res1.skipped_count == 0
    assert len(fake.download_calls) == 2

    # Check files exist on disk
    src_folder = music_root / source.folder_name
    assert (src_folder / "Song 1 [vid1].mp3").exists()
    assert (src_folder / "Song 2 [vid2].mp3").exists()

    # Verify DB states
    items_db = repo.get_items_by_source(source.id)
    assert len(items_db) == 2
    assert all(it.status == ItemStatus.DOWNLOADED for it in items_db)

    # 2. Second sync with NO changes: downloads 0 items (idempotence)
    fake.download_calls.clear()
    res2 = sync_source_service(
        repo=repo,
        source_adapter=fake,
        source_id=source.id,
        music_root=music_root,
    )
    assert res2.downloaded_count == 0
    assert res2.skipped_count == 2
    assert len(fake.download_calls) == 0

    # 3. Add a new item (vid3) to remote: downloads ONLY vid3
    fake.items.append(RemoteItem(external_id="vid3", title="Song 3", position=3, url="http://v3"))
    fake.download_calls.clear()
    res3 = sync_source_service(
        repo=repo,
        source_adapter=fake,
        source_id=source.id,
        music_root=music_root,
    )
    assert res3.downloaded_count == 1
    assert res3.skipped_count == 2
    assert fake.download_calls == ["vid3"]
    assert (src_folder / "Song 3 [vid3].mp3").exists()

    # 4. Reorder playlist (swap vid1 and vid2 positions): 0 downloads, positions updated
    fake.items = [
        RemoteItem(external_id="vid2", title="Song 2", position=1, url="http://v2"),
        RemoteItem(external_id="vid1", title="Song 1", position=2, url="http://v1"),
        RemoteItem(external_id="vid3", title="Song 3", position=3, url="http://v3"),
    ]
    fake.download_calls.clear()
    res4 = sync_source_service(
        repo=repo,
        source_adapter=fake,
        source_id=source.id,
        music_root=music_root,
    )
    assert res4.downloaded_count == 0
    assert res4.skipped_count == 3
    items_reordered = {it.external_id: it for it in repo.get_items_by_source(source.id)}
    assert items_reordered["vid2"].position == 1
    assert items_reordered["vid1"].position == 2


def test_sync_private_playlist_fails_early(tmp_path: Path) -> None:
    db_path = tmp_path / "priv.sqlite3"
    repo = SQLiteRepo(db_path)

    fake = FakeSource(is_private=True)
    with pytest.raises(AppError) as exc:
        add_source_service(repo, fake, "https://youtube.com/playlist?list=PLpriv")
    assert exc.value.code == ErrorCode.PRIVATE_SOURCE


def test_sync_safety_threshold_aborts(tmp_path: Path) -> None:
    """When a remote drops from 10 items to 1 item, abort and leave DB untouched."""
    db_path = tmp_path / "shrink.sqlite3"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_path)

    items = [
        RemoteItem(external_id=f"vid_{i}", title=f"Song {i}", position=i, url=f"http://v{i}")
        for i in range(1, 11)
    ]
    fake = FakeSource(title="Big Playlist", items=items)
    source = add_source_service(repo, fake, "https://youtube.com/playlist?list=PLshrink")

    # Initial sync with 10 items
    sync_source_service(repo, fake, source.id, music_root)
    src_db = repo.get_source(source.id)
    assert src_db is not None
    assert src_db.last_known_count == 10

    # Shrink remote to 1 item
    fake.items = [items[0]]
    with pytest.raises(AppError) as exc:
        sync_source_service(repo, fake, source.id, music_root, safety_threshold=0.50)
    assert exc.value.code == ErrorCode.EMPTY_OR_SHRUNK

    # Source was marked with ERROR and DB items were not altered
    src_after = repo.get_source(source.id)
    assert src_after is not None
    assert src_after.status == SourceStatus.ERROR
    assert len(repo.get_items_by_source(source.id)) == 10


def test_sync_item_failure_recorded(tmp_path: Path) -> None:
    """When an item download fails, error status and attempts are stored in DB."""
    db_path = tmp_path / "fail.sqlite3"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_path)

    items = [
        RemoteItem(external_id="vid_good", title="Good Song", position=1, url="http://vg"),
        RemoteItem(external_id="vid_bad", title="Bad Song", position=2, url="http://vb"),
    ]
    fake = FakeSource(title="Fail Test", items=items, fail_downloads={"vid_bad"})
    source = add_source_service(repo, fake, "https://youtube.com/playlist?list=PLfail")

    res = sync_source_service(repo, fake, source.id, music_root)
    assert res.downloaded_count == 1
    assert res.failed_count == 1

    items_db = {it.external_id: it for it in repo.get_items_by_source(source.id)}
    assert items_db["vid_good"].status == ItemStatus.DOWNLOADED
    assert items_db["vid_bad"].status == ItemStatus.ERROR
    assert items_db["vid_bad"].attempts == 1
    assert items_db["vid_bad"].error_code == ErrorCode.NETWORK


def test_sync_reappearing_removed_item_restores_flag_and_m3u8(tmp_path: Path) -> None:
    """H-13: If a removed_remote=1 item reappears in the playlist, it returns to removed_remote=0 and .m3u8."""
    db_path = tmp_path / "reappear.sqlite3"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_path)

    all_three = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://v1"),
        RemoteItem(external_id="vid2", title="Song 2", position=2, url="http://v2"),
        RemoteItem(external_id="vid3", title="Song 3", position=3, url="http://v3"),
    ]
    fake = FakeSource(title="Reappear Playlist", items=list(all_three))
    source = add_source_service(repo, fake, "https://youtube.com/playlist?list=PLreappear")

    # 1. Sync all 3 items
    sync_source_service(repo, fake, source.id, music_root)
    m3u8_path = music_root / source.folder_name / f"{source.folder_name}.m3u8"
    assert "Song 3 [vid3].mp3" in m3u8_path.read_text(encoding="utf-8")

    # 2. Remove vid3 remotely (2 of 3 remain = 66.7% >= 50%)
    fake.items = all_three[:2]
    sync_source_service(repo, fake, source.id, music_root)
    items_after_remove = {it.external_id: it for it in repo.get_items_by_source(source.id)}
    assert items_after_remove["vid3"].removed_remote is True
    assert "Song 3 [vid3].mp3" not in m3u8_path.read_text(encoding="utf-8")

    # 3. vid3 reappears in the remote playlist
    fake.items = list(all_three)
    fake.download_calls.clear()
    sync_source_service(repo, fake, source.id, music_root)

    items_after_reappear = {it.external_id: it for it in repo.get_items_by_source(source.id)}
    assert items_after_reappear["vid3"].removed_remote is False
    assert "Song 3 [vid3].mp3" in m3u8_path.read_text(encoding="utf-8")
    assert fake.download_calls == []


def test_sync_downloaded_item_with_missing_file_returns_to_pending(tmp_path: Path) -> None:
    """H-13: A DOWNLOADED item whose file no longer exists on disk returns to pending (and redownloads)."""
    db_path = tmp_path / "missing_file.sqlite3"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_path)

    items = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://v1"),
        RemoteItem(external_id="vid2", title="Song 2", position=2, url="http://v2"),
    ]
    fake = FakeSource(title="Missing File Playlist", items=items)
    source = add_source_service(repo, fake, "https://youtube.com/playlist?list=PLmissing")

    # 1. Initial sync downloads both
    sync_source_service(repo, fake, source.id, music_root)
    mp3_vid1 = music_root / source.folder_name / "Song 1 [vid1].mp3"
    assert mp3_vid1.exists()

    # Simulate external loss of Song 1 [vid1].mp3 on disk and make its redownload fail first
    # so we can observe it transitioned out of DOWNLOADED, then allow redownload to succeed
    mp3_vid1.unlink()
    assert not mp3_vid1.exists()

    # If vid1 is temporarily absent from remote (only vid2 present, threshold 0.5 allows 1 of 2),
    # vid1 with missing file must become PENDING in DB
    fake.items = [items[1]]
    sync_source_service(repo, fake, source.id, music_root)
    items_db = {it.external_id: it for it in repo.get_items_by_source(source.id)}
    assert items_db["vid1"].status == ItemStatus.PENDING

    # When vid1 is present in remote, it is redownloaded and restored on disk
    fake.items = items
    fake.download_calls.clear()
    res = sync_source_service(repo, fake, source.id, music_root)
    assert res.downloaded_count == 1
    assert fake.download_calls == ["vid1"]
    assert mp3_vid1.exists()
