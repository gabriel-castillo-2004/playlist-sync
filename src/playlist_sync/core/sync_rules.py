"""Domain rules for incremental playlist synchronization (RF-5, RF-8, RF-12)."""

from __future__ import annotations

import math

from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import ItemRecord, ItemStatus, RemoteItem, SyncPlan


def evaluate_remote_safety(
    last_known_count: int,
    remote_count: int,
    safety_threshold: float = 0.50,
) -> None:
    """Enforce RF-12 safety threshold against accidental deletion / YouTube glitches.

    If remote count drops to 0 or is below threshold percentage of last known count,
    the sync must be aborted without modifying local state.
    """
    if last_known_count > 0:
        if remote_count == 0:
            raise AppError(
                code=ErrorCode.EMPTY_OR_SHRUNK,
                technical_detail=f"Remote returned 0 items but last known count was {last_known_count}.",
                retryable=False,
            )
        min_allowed = math.ceil(last_known_count * safety_threshold)
        if remote_count < last_known_count * safety_threshold:
            raise AppError(
                code=ErrorCode.EMPTY_OR_SHRUNK,
                technical_detail=(
                    f"Remote returned {remote_count} items, which is under the safety threshold "
                    f"({min_allowed} items, {int(safety_threshold * 100)}% of {last_known_count})."
                ),
                retryable=False,
            )


def calculate_sync_plan(
    existing_items: dict[str, ItemRecord],
    remote_items: list[RemoteItem],
    max_retries: int = 3,
    missing_file_external_ids: set[str] | None = None,
) -> SyncPlan:
    """Calculate the incremental work to perform for a source synchronization.

    - Identifies which items need to be downloaded (RF-5, RF-8).
    - Identifies position changes to keep playlist files synced.
    - Identifies remote items that were removed without deleting their files (RF-12).
    - Identifies removed_remote items that reappeared in the remote playlist (H-13).
    """
    remote_map = {item.external_id: item for item in remote_items}
    missing_ids = missing_file_external_ids or set()
    items_to_download: list[RemoteItem] = []
    items_to_update_pos: list[tuple[ItemRecord, int]] = []
    items_to_mark_removed: list[ItemRecord] = []
    items_to_restore: list[ItemRecord] = []

    for remote_item in remote_items:
        existing = existing_items.get(remote_item.external_id)
        if existing is None:
            # Completely new item
            items_to_download.append(remote_item)
        else:
            # Check if position changed
            if existing.position != remote_item.position:
                items_to_update_pos.append((existing, remote_item.position))

            # Check download status
            if existing.status == ItemStatus.DOWNLOADED:
                if existing.external_id in missing_ids or not existing.file_path:
                    items_to_download.append(remote_item)
                else:
                    if existing.removed_remote:
                        items_to_restore.append(existing)
                    continue
            elif existing.status in (ItemStatus.PENDING, ItemStatus.DOWNLOADING):
                items_to_download.append(remote_item)
            elif existing.status == ItemStatus.ERROR:
                if existing.attempts < max_retries:
                    items_to_download.append(remote_item)
                elif existing.removed_remote:
                    items_to_restore.append(existing)
                # If attempts >= max_retries, do not auto-retry

    # Check for removed items
    for ext_id, existing in existing_items.items():
        if ext_id not in remote_map and not existing.removed_remote:
            items_to_mark_removed.append(existing)

    return SyncPlan(
        items_to_download=items_to_download,
        items_to_mark_removed=items_to_mark_removed,
        items_to_update_position=items_to_update_pos,
        total_remote=len(remote_items),
        items_to_restore=items_to_restore,
    )
