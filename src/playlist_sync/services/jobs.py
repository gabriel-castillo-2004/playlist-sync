"""Background job executor with concurrency lock and SSE event broadcaster (RF-10, RF-11)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import (
    ItemStatus,
    Library,
    Progress,
    Source,
)
from playlist_sync.services.sync import sync_source_service

logger = logging.getLogger(__name__)


class SSEBroadcaster:
    """Manages active SSE client connections and broadcasts real-time events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Register a new client subscriber and yield SSE messages."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)

        try:
            # Send initial ping event
            yield "event: ping\ndata: {}\n\n"
            while True:
                msg = await queue.get()
                yield msg
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an event to all connected subscribers."""
        formatted = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        async with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(formatted)
                except asyncio.QueueFull:
                    # Drop old messages for lagging clients
                    pass


class JobExecutor:
    """Orchestrates background sync jobs with an exclusive lock (RF-11)."""

    def __init__(
        self,
        repo: SQLiteRepo,
        source_adapter: Source,
        music_root: Path,
        library: Library | None = None,
        broadcaster: SSEBroadcaster | None = None,
        safety_threshold: float = 0.50,
        max_retries: int = 3,
        min_disk_free_mb: int = 1024,
    ) -> None:
        self.repo = repo
        self.source_adapter = source_adapter
        self.music_root = music_root
        self.library = library or LocalLibrary(music_root)
        self.broadcaster = broadcaster or SSEBroadcaster()
        self.safety_threshold = safety_threshold
        self.max_retries = max_retries
        self.min_disk_free_mb = min_disk_free_mb

        self._lock = asyncio.Lock()
        self._current_source_id: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Check if a synchronization job is currently executing."""
        return self._lock.locked()

    @property
    def current_source_id(self) -> int | None:
        return self._current_source_id

    async def wait_idle(self, timeout: float = 10.0) -> None:
        """Wait until current background synchronization finishes."""
        if self._current_task and not self._current_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._current_task), timeout=timeout)
            except TimeoutError:
                pass

    def _sync_progress_callback(self, source_id: int, p: Progress) -> None:
        """Bridge sync progress callback from thread pool to async SSE broadcaster."""
        if self._loop and self._loop.is_running():
            data = {
                "source_id": source_id,
                "status": p.status,
                "percentage": round(p.percentage, 1),
                "speed_bytes_sec": p.speed_bytes_per_sec,
                "current_track": p.current_item_title,
                "item_index": p.item_index,
                "total_to_download": p.total_to_download,
            }
            asyncio.run_coroutine_threadsafe(
                self.broadcaster.emit("progress", data),
                self._loop,
            )

    async def trigger_sync(self, source_id: int) -> bool:
        """Start synchronization for a specific source. Fails if a job is already active."""
        if self._lock.locked():
            raise AppError(
                code=ErrorCode.UNKNOWN,
                user_message="Ya hay una sincronización en curso. Por favor espera a que termine.",
                technical_detail="Conflict: JobExecutor lock is currently held.",
                retryable=True,
            )

        await self._lock.acquire()
        self._loop = asyncio.get_running_loop()
        try:
            self._current_task = asyncio.create_task(self._run_sync_task(source_id))
        except Exception:
            self._lock.release()
            raise
        return True

    async def trigger_sync_all(self) -> bool:
        """Start sequential synchronization for all tracked sources."""
        if self._lock.locked():
            raise AppError(
                code=ErrorCode.UNKNOWN,
                user_message="Ya hay una sincronización en curso. Por favor espera a que termine.",
                technical_detail="Conflict: JobExecutor lock is currently held.",
                retryable=True,
            )

        await self._lock.acquire()
        self._loop = asyncio.get_running_loop()
        try:
            self._current_task = asyncio.create_task(self._run_sync_all_task())
        except Exception:
            self._lock.release()
            raise
        return True

    async def retry_item(self, item_id: int) -> bool:
        """Reset attempts on an error item and trigger a sync of its source (H-12)."""
        item = self.repo.get_item(item_id)
        if not item:
            raise AppError(
                code=ErrorCode.SOURCE_NOT_FOUND,
                user_message="El elemento solicitado no existe.",
                technical_detail=f"Item {item_id} not found in database.",
            )

        if self._lock.locked():
            raise AppError(
                code=ErrorCode.UNKNOWN,
                user_message="Ya hay una sincronización en curso. Por favor espera a que termine.",
                technical_detail="Conflict: JobExecutor lock is currently held.",
                retryable=True,
            )

        # Reset item status to pending with 0 attempts only after verifying lock is free
        self.repo.update_item_status(
            item_id=item_id,
            status=ItemStatus.PENDING,
            error_code=None,
            error_message=None,
            reset_attempts=True,
        )
        return await self.trigger_sync(item.source_id)

    async def _run_sync_task(self, source_id: int) -> None:
        """Internal execution of single source sync within the exclusive lock."""
        try:
            self._current_source_id = source_id
            await self.broadcaster.emit("sync_started", {"source_id": source_id})
            try:
                # Run CPU/network blocking sync in worker thread
                result = await asyncio.to_thread(
                    sync_source_service,
                    repo=self.repo,
                    source_adapter=self.source_adapter,
                    source_id=source_id,
                    music_root=self.music_root,
                    library=self.library,
                    on_progress=lambda p: self._sync_progress_callback(source_id, p),
                    min_free_mb=self.min_disk_free_mb,
                    safety_threshold=self.safety_threshold,
                    max_retries=self.max_retries,
                )
                await self.broadcaster.emit(
                    "sync_completed",
                    {
                        "source_id": source_id,
                        "downloaded": result.downloaded_count,
                        "skipped": result.skipped_count,
                        "failed": result.failed_count,
                    },
                )
            except AppError as err:
                logger.error("Sync error for source %s: %s", source_id, err)
                await self.broadcaster.emit(
                    "sync_failed",
                    {
                        "source_id": source_id,
                        "error_code": err.code,
                        "message": err.user_message,
                    },
                )
            except Exception as exc:
                logger.exception("Unexpected error syncing source %s: %s", source_id, exc)
                await self.broadcaster.emit(
                    "sync_failed",
                    {
                        "source_id": source_id,
                        "error_code": ErrorCode.UNKNOWN,
                        "message": "Ocurrió un problema inesperado durante la sincronización.",
                    },
                )
        finally:
            self._current_source_id = None
            if self._lock.locked():
                self._lock.release()

    async def _run_sync_all_task(self) -> None:
        """Internal execution of sequential sync for all sources within the lock."""
        try:
            sources = self.repo.list_sources()
            await self.broadcaster.emit("sync_all_started", {"total_sources": len(sources)})
            for src in sources:
                self._current_source_id = src.id
                src_id = src.id
                await self.broadcaster.emit("sync_started", {"source_id": src_id})

                def make_cb(target_id: int) -> Callable[[Progress], None]:
                    return lambda p: self._sync_progress_callback(target_id, p)

                try:
                    res = await asyncio.to_thread(
                        sync_source_service,
                        repo=self.repo,
                        source_adapter=self.source_adapter,
                        source_id=src_id,
                        music_root=self.music_root,
                        library=self.library,
                        on_progress=make_cb(src_id),
                        min_free_mb=self.min_disk_free_mb,
                        safety_threshold=self.safety_threshold,
                        max_retries=self.max_retries,
                    )
                    await self.broadcaster.emit(
                        "sync_completed",
                        {
                            "source_id": src.id,
                            "downloaded": res.downloaded_count,
                            "skipped": res.skipped_count,
                            "failed": res.failed_count,
                        },
                    )
                except AppError as err:
                    logger.warning("Sync error during sync-all for source %s: %s", src.id, err)
                    await self.broadcaster.emit(
                        "sync_failed",
                        {
                            "source_id": src.id,
                            "error_code": err.code,
                            "message": err.user_message,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Unexpected error during sync-all for source %s: %s", src.id, exc
                    )
                    await self.broadcaster.emit(
                        "sync_failed",
                        {
                            "source_id": src.id,
                            "error_code": ErrorCode.UNKNOWN,
                            "message": "Ocurrió un problema inesperado durante la sincronización.",
                        },
                    )
            await self.broadcaster.emit("sync_all_completed", {})
        finally:
            self._current_source_id = None
            if self._lock.locked():
                self._lock.release()
