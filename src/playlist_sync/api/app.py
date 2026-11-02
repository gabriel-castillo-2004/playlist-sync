"""FastAPI application factory and configuration."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from playlist_sync.adapters.composite_source import CompositeSource
from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.adapters.web import mount_web_adapter
from playlist_sync.api.routers import health, podcasts, sources, sse, sync
from playlist_sync.api.schemas import ErrorResponse
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import Library, Source
from playlist_sync.logging_config import setup_logging
from playlist_sync.services.jobs import JobExecutor, SSEBroadcaster
from playlist_sync.services.scheduler import PeriodicSyncScheduler

logger = logging.getLogger(__name__)


def create_app(
    repo: SQLiteRepo | None = None,
    source_adapter: Source | None = None,
    music_root: Path | str = "music_root",
    library: Library | None = None,
    broadcaster: SSEBroadcaster | None = None,
    safety_threshold: float = 0.50,
    max_retries: int = 3,
    min_disk_free_mb: int = 1024,
    interval_hours: float = 6.0,
    log_file: str = "playlist_sync.log",
    log_level: str = "INFO",
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    setup_logging(log_file=log_file, level_name=log_level, force=True)
    logger.info("Initializing Playlist Sync API...")

    resolved_music_root = Path(music_root).resolve()
    resolved_repo = repo or SQLiteRepo("playlist_sync.sqlite3")
    resolved_source = source_adapter or CompositeSource()
    resolved_library = library or LocalLibrary(resolved_music_root)
    resolved_broadcaster = broadcaster or SSEBroadcaster()

    job_executor = JobExecutor(
        repo=resolved_repo,
        source_adapter=resolved_source,
        music_root=resolved_music_root,
        library=resolved_library,
        broadcaster=resolved_broadcaster,
        safety_threshold=safety_threshold,
        max_retries=max_retries,
        min_disk_free_mb=min_disk_free_mb,
    )

    # Periodic background scheduler (RF-17)
    scheduler = PeriodicSyncScheduler(job_executor=job_executor, interval_hours=interval_hours)

    @asynccontextmanager
    async def app_lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        if interval_hours > 0:
            scheduler.start()
        yield
        if interval_hours > 0:
            await scheduler.stop()

    app = FastAPI(
        title="Playlist Sync API",
        version="0.1.0",
        description="Local API for managing and synchronizing YouTube playlists and podcasts.",
        lifespan=app_lifespan,
    )

    # Store state on application instance
    app.state.repo = resolved_repo
    app.state.source_adapter = resolved_source
    app.state.music_root = resolved_music_root
    app.state.library = resolved_library
    app.state.broadcaster = resolved_broadcaster
    app.state.job_executor = job_executor
    app.state.min_disk_free_mb = min_disk_free_mb
    app.state.scheduler = scheduler

    # Global AppError exception handler
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        if exc.technical_detail:
            logger.warning(
                "API AppError [%s]: %s | technical_detail=%s",
                exc.code,
                exc.user_message,
                exc.technical_detail,
            )
        status_map = {
            ErrorCode.SOURCE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
            ErrorCode.INVALID_URL: status.HTTP_400_BAD_REQUEST,
            ErrorCode.PRIVATE_SOURCE: status.HTTP_400_BAD_REQUEST,
            ErrorCode.DISK_FULL: status.HTTP_507_INSUFFICIENT_STORAGE,
        }
        http_status = status_map.get(exc.code, status.HTTP_400_BAD_REQUEST)
        error_body = ErrorResponse(
            code=exc.code,
            user_message=exc.user_message,
        ).model_dump(exclude_none=True)
        return JSONResponse(status_code=http_status, content=error_body)

    # Register routers
    app.include_router(sources.router)
    app.include_router(sync.router)
    app.include_router(sse.router)
    app.include_router(health.router)
    app.include_router(podcasts.router)

    # Mount web frontend adapter and cover endpoints
    mount_web_adapter(app, music_root=resolved_music_root)

    return app
