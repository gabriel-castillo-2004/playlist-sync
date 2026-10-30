"""FastAPI application factory and configuration."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.adapters.ytdlp_source import YtDlpSource
from playlist_sync.api.routers import health, sources, sse, sync
from playlist_sync.api.schemas import ErrorResponse
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import Library, Source
from playlist_sync.logging_config import setup_logging
from playlist_sync.services.jobs import JobExecutor, SSEBroadcaster

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
    log_file: str = "playlist_sync.log",
    log_level: str = "INFO",
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    setup_logging(log_file=log_file, level_name=log_level, force=True)
    logger.info("Initializing Playlist Sync API...")

    app = FastAPI(
        title="Playlist Sync API",
        version="0.1.0",
        description="Local API for managing and synchronizing YouTube playlists and podcasts.",
    )

    # CORS for local web UI
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    resolved_music_root = Path(music_root).resolve()
    resolved_repo = repo or SQLiteRepo("playlist_sync.sqlite3")
    resolved_source = source_adapter or YtDlpSource()
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

    # Store state on application instance
    app.state.repo = resolved_repo
    app.state.source_adapter = resolved_source
    app.state.music_root = resolved_music_root
    app.state.library = resolved_library
    app.state.broadcaster = resolved_broadcaster
    app.state.job_executor = job_executor
    app.state.min_disk_free_mb = min_disk_free_mb

    # Global AppError exception handler
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
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
            technical_detail=exc.technical_detail,
        ).model_dump()
        return JSONResponse(status_code=http_status, content=error_body)

    # Register routers
    app.include_router(sources.router)
    app.include_router(sync.router)
    app.include_router(sse.router)
    app.include_router(health.router)

    return app
