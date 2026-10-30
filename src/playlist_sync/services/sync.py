"""Synchronization service coordinating domain rules, repo and source adapters."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.errors import AppError, ErrorCode, classify_ytdlp_error
from playlist_sync.core.models import (
    ItemStatus,
    Library,
    Progress,
    RemoteItem,
    Source,
    SourceRecord,
    SourceStatus,
    SyncResult,
)
from playlist_sync.core.sync_rules import calculate_sync_plan, evaluate_remote_safety

logger = logging.getLogger(__name__)


def check_disk_space_available(target_dir: Path, min_mb: int = 1024) -> None:
    """Check that the target filesystem has at least min_mb available."""
    target = target_dir if target_dir.exists() else target_dir.parent
    try:
        usage = shutil.disk_usage(target)
        free_mb = usage.free // (1024 * 1024)
        if free_mb < min_mb:
            raise AppError(
                ErrorCode.DISK_FULL,
                technical_detail=f"Only {free_mb} MB free, minimum required is {min_mb} MB.",
            )
    except AppError:
        raise
    except Exception as exc:
        logger.warning("Could not verify disk space: %s", exc)


def add_source_service(
    repo: SQLiteRepo,
    source_adapter: Source,
    url: str,
) -> SourceRecord:
    """Inspect and add a new source to the database."""
    # Check if already registered
    existing = repo.get_source_by_url(url)
    if existing:
        return existing

    info = source_adapter.inspect(url)
    return repo.add_source(
        kind=info.kind,
        url=info.url,
        title=info.title,
        cover_url=info.cover_url,
    )


def sync_source_service(
    repo: SQLiteRepo,
    source_adapter: Source,
    source_id: int,
    music_root: Path,
    library: Library | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    min_free_mb: int = 1024,
    safety_threshold: float = 0.50,
    max_retries: int = 3,
) -> SyncResult:
    """Perform incremental synchronization of a source."""
    source = repo.get_source(source_id)
    if not source:
        raise AppError(
            ErrorCode.SOURCE_NOT_FOUND,
            technical_detail=f"Source ID {source_id} does not exist in local database.",
        )

    lib = library or LocalLibrary(music_root)
    dest_dir = music_root / source.folder_name
    check_disk_space_available(dest_dir, min_mb=min_free_mb)

    repo.update_source_status(source_id, SourceStatus.SYNCING)

    try:
        remote_items: list[RemoteItem] = source_adapter.list_items(source)
    except Exception as exc:
        app_err = exc if isinstance(exc, AppError) else classify_ytdlp_error(exc)
        repo.update_source_status(
            source_id,
            SourceStatus.ERROR,
            error_code=app_err.code,
            error_message=app_err.user_message,
        )
        raise app_err from exc

    # Enforce safety threshold (RF-12)
    try:
        evaluate_remote_safety(
            last_known_count=source.last_known_count,
            remote_count=len(remote_items),
            safety_threshold=safety_threshold,
        )
    except AppError as safety_err:
        repo.update_source_status(
            source_id,
            SourceStatus.ERROR,
            error_code=safety_err.code,
            error_message=safety_err.user_message,
        )
        raise safety_err

    existing_items = {it.external_id: it for it in repo.get_items_by_source(source_id)}
    plan = calculate_sync_plan(existing_items, remote_items, max_retries=max_retries)

    # 1. Update position changes without renaming files
    for item_rec, new_pos in plan.items_to_update_position:
        repo.update_item_position(item_rec.id, new_pos)
        if item_rec.file_path and hasattr(lib, "update_track_position_tag"):
            lib.update_track_position_tag(Path(item_rec.file_path), new_pos, len(remote_items))

    # 2. Mark removed remote items without deleting files (RF-12)
    for removed_rec in plan.items_to_mark_removed:
        repo.mark_item_removed_remote(removed_rec.id)

    downloaded_count = 0
    failed_count = 0
    failed_items: list[tuple[str, str]] = []

    # 3. Download items sequentially (RNF-4)
    for remote_item in plan.items_to_download:
        db_item = repo.upsert_item(
            source_id=source_id,
            external_id=remote_item.external_id,
            title=remote_item.title,
            position=remote_item.position,
            published_at=remote_item.published_at,
        )
        repo.update_item_status(db_item.id, ItemStatus.DOWNLOADING)

        try:
            downloaded = source_adapter.download(
                item=remote_item,
                dest_dir=dest_dir,
                on_progress=on_progress,
            )
            final_path = lib.finalize_item(
                source=source,
                item=db_item,
                file=downloaded,
                total_items=len(remote_items),
            )
            repo.update_item_status(
                item_id=db_item.id,
                status=ItemStatus.DOWNLOADED,
                file_path=str(final_path),
                increment_attempts=True,
            )
            downloaded_count += 1
        except Exception as exc:
            app_err = exc if isinstance(exc, AppError) else classify_ytdlp_error(exc)
            repo.update_item_status(
                item_id=db_item.id,
                status=ItemStatus.ERROR,
                error_code=app_err.code,
                error_message=app_err.user_message,
                increment_attempts=True,
            )
            failed_count += 1
            failed_items.append((remote_item.external_id, app_err.user_message))

    # 4. Regenerate .m3u8 playlist file (Section 6.2)
    all_source_items = repo.get_items_by_source(source_id)
    try:
        lib.rebuild_playlist_file(source=source, items=all_source_items)
    except Exception as exc:
        logger.warning("Could not rebuild playlist file for source %s: %s", source_id, exc)

    # Conclude source sync status
    final_status = SourceStatus.IDLE if failed_count == 0 else SourceStatus.ERROR
    last_err_code = None if failed_count == 0 else ErrorCode.UNKNOWN
    last_err_msg = None if failed_count == 0 else f"{failed_count} elementos fallaron al descargar."

    repo.update_source_status(
        source_id=source_id,
        status=final_status,
        error_code=last_err_code,
        error_message=last_err_msg,
        last_known_count=len(remote_items),
    )

    return SyncResult(
        source_id=source_id,
        total_remote=len(remote_items),
        downloaded_count=downloaded_count,
        skipped_count=len(remote_items) - len(plan.items_to_download),
        failed_count=failed_count,
        removed_count=len(plan.items_to_mark_removed),
        failed_items=failed_items,
    )
