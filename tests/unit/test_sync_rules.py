"""Unit tests for incremental sync rules and safety threshold (RF-5, RF-8, RF-12)."""

import pytest

from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import ItemRecord, ItemStatus, RemoteItem
from playlist_sync.core.sync_rules import calculate_sync_plan, evaluate_remote_safety


def test_evaluate_safety_drops_to_zero() -> None:
    """If remote returns 0 items and last known count > 0, raise EMPTY_OR_SHRUNK."""
    with pytest.raises(AppError) as exc:
        evaluate_remote_safety(last_known_count=10, remote_count=0)
    assert exc.value.code == ErrorCode.EMPTY_OR_SHRUNK


def test_evaluate_safety_drops_below_threshold() -> None:
    """If remote drops below 50% of last known count, raise EMPTY_OR_SHRUNK."""
    with pytest.raises(AppError) as exc:
        evaluate_remote_safety(last_known_count=100, remote_count=49, safety_threshold=0.50)
    assert exc.value.code == ErrorCode.EMPTY_OR_SHRUNK


def test_evaluate_safety_above_or_equal_threshold() -> None:
    """If remote is >= 50% of last known count, safety check passes."""
    evaluate_remote_safety(last_known_count=100, remote_count=50, safety_threshold=0.50)
    evaluate_remote_safety(last_known_count=100, remote_count=105, safety_threshold=0.50)


def test_evaluate_safety_first_sync() -> None:
    """If last known count is 0 (first sync), no threshold violation is triggered."""
    evaluate_remote_safety(last_known_count=0, remote_count=10)
    evaluate_remote_safety(last_known_count=0, remote_count=0)


@pytest.mark.parametrize(
    ("last_known", "remote_count"),
    [
        (3, 1),
        (5, 2),
        (7, 3),
    ],
)
def test_evaluate_safety_odd_counts_abort_below_half(last_known: int, remote_count: int) -> None:
    """H-05: 3->1 (33%), 5->2 (40%), and 7->3 (42.8%) must abort with EMPTY_OR_SHRUNK."""
    with pytest.raises(AppError) as exc:
        evaluate_remote_safety(
            last_known_count=last_known, remote_count=remote_count, safety_threshold=0.50
        )
    assert exc.value.code == ErrorCode.EMPTY_OR_SHRUNK


def test_evaluate_safety_exact_half_passes() -> None:
    """H-05: 4->2 (50% exact) and 3->2 (66.7%), 5->3 (60%), 7->4 (57.1%) must not abort."""
    evaluate_remote_safety(last_known_count=4, remote_count=2, safety_threshold=0.50)
    evaluate_remote_safety(last_known_count=3, remote_count=2, safety_threshold=0.50)
    evaluate_remote_safety(last_known_count=5, remote_count=3, safety_threshold=0.50)
    evaluate_remote_safety(last_known_count=7, remote_count=4, safety_threshold=0.50)


def test_calculate_sync_plan_all_new() -> None:
    """When DB has no items, all remote items are scheduled for download."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://vid1"),
        RemoteItem(external_id="vid2", title="Song 2", position=2, url="http://vid2"),
    ]
    plan = calculate_sync_plan(existing_items={}, remote_items=remotes)
    assert len(plan.items_to_download) == 2
    assert plan.total_remote == 2
    assert len(plan.items_to_mark_removed) == 0


def test_calculate_sync_plan_idempotent() -> None:
    """When all items are downloaded, 0 items are scheduled for download."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://vid1"),
    ]
    existing = {
        "vid1": ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Song 1",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song 1 [vid1].mp3",
            downloaded_at=None,
            removed_remote=False,
        )
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes)
    assert len(plan.items_to_download) == 0
    assert len(plan.items_to_mark_removed) == 0


def test_calculate_sync_plan_incremental_new_item() -> None:
    """When a new item is added to the remote, only that item is scheduled."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://vid1"),
        RemoteItem(external_id="vid2", title="Song 2", position=2, url="http://vid2"),
    ]
    existing = {
        "vid1": ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Song 1",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song 1 [vid1].mp3",
            downloaded_at=None,
            removed_remote=False,
        )
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes)
    assert len(plan.items_to_download) == 1
    assert plan.items_to_download[0].external_id == "vid2"


def test_calculate_sync_plan_retry_limit() -> None:
    """Failed items under max_retries are retried; items at max_retries are skipped."""
    remotes = [
        RemoteItem(external_id="err_under", title="Song Under", position=1, url="http://u"),
        RemoteItem(external_id="err_max", title="Song Max", position=2, url="http://m"),
    ]
    existing = {
        "err_under": ItemRecord(
            id=1,
            source_id=1,
            external_id="err_under",
            title="Song Under",
            position=1,
            published_at=None,
            status=ItemStatus.ERROR,
            error_code=ErrorCode.NETWORK,
            error_message="timeout",
            attempts=2,
            file_path=None,
            downloaded_at=None,
            removed_remote=False,
        ),
        "err_max": ItemRecord(
            id=2,
            source_id=1,
            external_id="err_max",
            title="Song Max",
            position=2,
            published_at=None,
            status=ItemStatus.ERROR,
            error_code=ErrorCode.NETWORK,
            error_message="timeout",
            attempts=3,
            file_path=None,
            downloaded_at=None,
            removed_remote=False,
        ),
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes, max_retries=3)
    assert len(plan.items_to_download) == 1
    assert plan.items_to_download[0].external_id == "err_under"


def test_calculate_sync_plan_removed_remote() -> None:
    """Items no longer in remote list are marked for removal without deleting files."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://vid1"),
    ]
    existing = {
        "vid1": ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Song 1",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song 1 [vid1].mp3",
            downloaded_at=None,
            removed_remote=False,
        ),
        "vid_gone": ItemRecord(
            id=2,
            source_id=1,
            external_id="vid_gone",
            title="Song Gone",
            position=2,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song Gone [vid_gone].mp3",
            downloaded_at=None,
            removed_remote=False,
        ),
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes)
    assert len(plan.items_to_mark_removed) == 1
    assert plan.items_to_mark_removed[0].external_id == "vid_gone"


def test_calculate_sync_plan_position_update() -> None:
    """When remote items are reordered, position updates are scheduled."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=2, url="http://vid1"),
    ]
    existing = {
        "vid1": ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Song 1",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song 1 [vid1].mp3",
            downloaded_at=None,
            removed_remote=False,
        ),
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes)
    assert len(plan.items_to_download) == 0
    assert len(plan.items_to_update_position) == 1
    assert plan.items_to_update_position[0][1] == 2


def test_calculate_sync_plan_reappearing_removed_item_is_restored() -> None:
    """H-13: An item with removed_remote=True that reappears in remote_items is scheduled for restore."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://vid1"),
    ]
    existing = {
        "vid1": ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Song 1",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song 1 [vid1].mp3",
            downloaded_at=None,
            removed_remote=True,
        ),
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes)
    assert len(plan.items_to_download) == 0
    assert len(plan.items_to_restore) == 1
    assert plan.items_to_restore[0].external_id == "vid1"


def test_calculate_sync_plan_missing_disk_file_redownloads() -> None:
    """H-13: A DOWNLOADED item whose file is reported missing on disk is scheduled for download."""
    remotes = [
        RemoteItem(external_id="vid1", title="Song 1", position=1, url="http://vid1"),
    ]
    existing = {
        "vid1": ItemRecord(
            id=1,
            source_id=1,
            external_id="vid1",
            title="Song 1",
            position=1,
            published_at=None,
            status=ItemStatus.DOWNLOADED,
            error_code=None,
            error_message=None,
            attempts=1,
            file_path="music_root/Song 1 [vid1].mp3",
            downloaded_at=None,
            removed_remote=False,
        ),
    }
    plan = calculate_sync_plan(
        existing_items=existing,
        remote_items=remotes,
        missing_file_external_ids={"vid1"},
    )
    assert len(plan.items_to_download) == 1
    assert plan.items_to_download[0].external_id == "vid1"


def test_calculate_sync_plan_skips_non_retryable_errors_and_backoff_h12() -> None:
    """H-12: Non-retryable errors (AGE_RESTRICTED, GEO_BLOCKED) are not auto-retried; transient errors use growing backoff."""
    from playlist_sync.core.sync_rules import calculate_retry_backoff_seconds

    remotes = [
        RemoteItem(external_id="age_vid", title="Age Restricted", position=1, url="http://v1"),
        RemoteItem(external_id="geo_vid", title="Geo Blocked", position=2, url="http://v2"),
        RemoteItem(external_id="net_vid", title="Network Transient", position=3, url="http://v3"),
        RemoteItem(external_id="rate_vid", title="Rate Limited", position=4, url="http://v4"),
    ]
    existing = {
        "age_vid": ItemRecord(
            id=1,
            source_id=1,
            external_id="age_vid",
            title="Age Restricted",
            position=1,
            published_at=None,
            status=ItemStatus.ERROR,
            error_code=ErrorCode.AGE_RESTRICTED,
            error_message="Restricción de edad",
            attempts=1,
            file_path=None,
            downloaded_at=None,
        ),
        "geo_vid": ItemRecord(
            id=2,
            source_id=1,
            external_id="geo_vid",
            title="Geo Blocked",
            position=2,
            published_at=None,
            status=ItemStatus.ERROR,
            error_code=ErrorCode.GEO_BLOCKED,
            error_message="Bloqueado en tu país",
            attempts=1,
            file_path=None,
            downloaded_at=None,
        ),
        "net_vid": ItemRecord(
            id=3,
            source_id=1,
            external_id="net_vid",
            title="Network Transient",
            position=3,
            published_at=None,
            status=ItemStatus.ERROR,
            error_code=ErrorCode.NETWORK,
            error_message="Sin red",
            attempts=1,
            file_path=None,
            downloaded_at=None,
        ),
        "rate_vid": ItemRecord(
            id=4,
            source_id=1,
            external_id="rate_vid",
            title="Rate Limited",
            position=4,
            published_at=None,
            status=ItemStatus.ERROR,
            error_code=ErrorCode.RATE_LIMITED,
            error_message="Espera un poco",
            attempts=2,
            file_path=None,
            downloaded_at=None,
        ),
    }
    plan = calculate_sync_plan(existing_items=existing, remote_items=remotes, max_retries=3)
    scheduled_ids = [it.external_id for it in plan.items_to_download]
    assert scheduled_ids == ["net_vid", "rate_vid"]

    b1 = calculate_retry_backoff_seconds(1, base_seconds=1.0)
    b2 = calculate_retry_backoff_seconds(2, base_seconds=1.0)
    b3 = calculate_retry_backoff_seconds(3, base_seconds=1.0)
    assert 0 < b1 < b2 < b3
