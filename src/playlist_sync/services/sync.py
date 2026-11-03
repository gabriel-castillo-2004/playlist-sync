"""Synchronization service coordinating domain rules, repo and source adapters."""

from __future__ import annotations

import logging
import re
import shutil
import time
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
from playlist_sync.core.sync_rules import (
    calculate_retry_backoff_seconds,
    calculate_sync_plan,
    evaluate_remote_safety,
)

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
    """Inspect and add a new source to the database, populating initial pending items (RF-2, H-09)."""
    # Check if already registered
    existing = repo.get_source_by_url(url)
    if existing:
        return existing

    info = source_adapter.inspect(url)
    source = repo.add_source(
        kind=info.kind,
        url=info.url,
        title=info.title,
        cover_url=info.cover_url,
    )

    try:
        initial_items = source_adapter.list_items(source)
    except Exception as exc:
        logger.warning("Could not fetch initial item list while adding source %s: %s", url, exc)
        initial_items = []

    for remote_item in initial_items:
        repo.upsert_item(
            source_id=source.id,
            external_id=remote_item.external_id,
            title=remote_item.title,
            position=remote_item.position,
            published_at=remote_item.published_at,
            artist=remote_item.artist,
        )

    known_count = len(initial_items) if initial_items else (info.item_count or 0)
    if known_count > 0:
        source = repo.update_source_metadata(
            source_id=source.id,
            title=source.title,
            cover_url=source.cover_url,
            last_known_count=known_count,
        )

    return source


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
    retry_backoff_base: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
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
    missing_file_external_ids: set[str] = set()
    for ext_id, item_rec in existing_items.items():
        if item_rec.status == ItemStatus.DOWNLOADED:
            file_exists = False
            if item_rec.file_path:
                f_path = Path(item_rec.file_path)
                actual_path = f_path if f_path.is_absolute() else (music_root / f_path)
                if not actual_path.exists():
                    actual_path = dest_dir / f_path.name
                file_exists = actual_path.exists()
            if not file_exists:
                repo.reset_item_to_pending(item_rec.id)
                item_rec.status = ItemStatus.PENDING
                item_rec.file_path = None
                missing_file_external_ids.add(ext_id)

    plan = calculate_sync_plan(
        existing_items,
        remote_items,
        max_retries=max_retries,
        missing_file_external_ids=missing_file_external_ids,
    )

    # 0. Restore items that reappeared in the remote playlist (H-13)
    for restored_rec in plan.items_to_restore:
        repo.restore_item_removed_remote(restored_rec.id)

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
    total_to_download = len(plan.items_to_download)
    for item_idx, remote_item in enumerate(plan.items_to_download, start=1):
        prior_item = existing_items.get(remote_item.external_id)
        if (
            prior_item is not None
            and prior_item.status == ItemStatus.ERROR
            and prior_item.attempts > 0
            and prior_item.error_code in (ErrorCode.RATE_LIMITED, ErrorCode.NETWORK)
        ):
            wait_sec = calculate_retry_backoff_seconds(
                prior_item.attempts, base_seconds=retry_backoff_base
            )
            if wait_sec > 0:
                sleep_fn(wait_sec)

        db_item = repo.upsert_item(
            source_id=source_id,
            external_id=remote_item.external_id,
            title=remote_item.title,
            position=remote_item.position,
            published_at=remote_item.published_at,
            artist=remote_item.artist,
        )
        repo.update_item_status(db_item.id, ItemStatus.DOWNLOADING)

        item_progress_cb: Callable[[Progress], None] | None = None
        if on_progress is not None:

            def _make_item_cb(
                idx: int, total_dl: int, cb: Callable[[Progress], None]
            ) -> Callable[[Progress], None]:
                def _wrapped(p: Progress) -> None:
                    p.item_index = idx
                    p.total_to_download = total_dl
                    cb(p)

                return _wrapped

            item_progress_cb = _make_item_cb(item_idx, total_to_download, on_progress)

        try:
            downloaded = source_adapter.download(
                item=remote_item,
                dest_dir=dest_dir,
                on_progress=item_progress_cb,
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


_DISK_MP3_SUFFIX_RE = re.compile(r"^(?P<title>.+?)\s*\[(?P<ext_id>[^\[\]]+)\]\.mp3$", re.IGNORECASE)


def reconcile_disk_service(
    repo: SQLiteRepo,
    music_root: Path,
    source_id: int | None = None,
    library: Library | None = None,
) -> int:
    """Scan music_root and mark items whose [{external_id}].mp3 exists on disk as DOWNLOADED (RF-20)."""
    if source_id is not None:
        src = repo.get_source(source_id)
        if not src:
            raise AppError(
                ErrorCode.SOURCE_NOT_FOUND,
                technical_detail=f"Source ID {source_id} does not exist in local database.",
            )
        sources = [src]
    else:
        sources = repo.list_sources()

    if not sources or not music_root.exists():
        return 0

    lib = library or LocalLibrary(music_root)
    reconciled_total = 0

    # Build a fallback index of all *.mp3 files across music_root
    all_mp3s: list[Path] = [
        p for p in music_root.rglob("*.mp3") if p.is_file() and p.stat().st_size > 0
    ]

    for source in sources:
        source_dir = music_root / source.folder_name
        dir_mp3s: list[Path] = []
        if source_dir.exists() and source_dir.is_dir():
            dir_mp3s = sorted(
                p
                for p in source_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".mp3" and p.stat().st_size > 0
            )

        existing_items = {it.external_id: it for it in repo.get_items_by_source(source.id)}
        source_reconciled = 0

        # 1. Reconcile existing DB items for this source by matching [{external_id}].mp3 suffix
        for ext_id, item_rec in existing_items.items():
            suffix_lower = f"[{ext_id}].mp3".lower()
            matched_file: Path | None = None

            for candidate in dir_mp3s:
                if candidate.name.lower().endswith(suffix_lower):
                    matched_file = candidate
                    break
            if matched_file is None:
                for candidate in all_mp3s:
                    if candidate.name.lower().endswith(suffix_lower):
                        matched_file = candidate
                        break

            if matched_file is not None and (
                item_rec.status != ItemStatus.DOWNLOADED
                or item_rec.file_path != str(matched_file)
                or item_rec.error_code is not None
            ):
                repo.update_item_status(
                    item_id=item_rec.id,
                    status=ItemStatus.DOWNLOADED,
                    error_code=None,
                    error_message=None,
                    file_path=str(matched_file),
                )
                source_reconciled += 1

        # 2. Discover untracked [{external_id}].mp3 files inside source_dir (e.g. after sources.json import)
        next_pos = max((it.position for it in existing_items.values()), default=0) + 1
        for candidate in dir_mp3s:
            m = _DISK_MP3_SUFFIX_RE.match(candidate.name)
            if not m:
                continue
            ext_id = m.group("ext_id")
            if ext_id in existing_items:
                continue
            parsed_title = m.group("title").strip() or ext_id
            new_item = repo.upsert_item(
                source_id=source.id,
                external_id=ext_id,
                title=parsed_title,
                position=next_pos,
            )
            repo.update_item_status(
                item_id=new_item.id,
                status=ItemStatus.DOWNLOADED,
                error_code=None,
                error_message=None,
                file_path=str(candidate),
            )
            existing_items[ext_id] = new_item
            next_pos += 1
            source_reconciled += 1

        if source_reconciled > 0:
            reconciled_total += source_reconciled
            updated_items = repo.get_items_by_source(source.id)
            try:
                lib.rebuild_playlist_file(source=source, items=updated_items)
            except Exception as exc:
                logger.warning(
                    "Could not rebuild playlist file during reconcile for source %s: %s",
                    source.id,
                    exc,
                )

    return reconciled_total
