"""FastAPI dependency providers."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.models import Source
from playlist_sync.services.jobs import JobExecutor, SSEBroadcaster


def get_repo(request: Request) -> SQLiteRepo:
    return request.app.state.repo  # type: ignore[no-any-return]


def get_music_root(request: Request) -> Path:
    return request.app.state.music_root  # type: ignore[no-any-return]


def get_job_executor(request: Request) -> JobExecutor:
    return request.app.state.job_executor  # type: ignore[no-any-return]


def get_source_adapter(request: Request) -> Source:
    return request.app.state.source_adapter  # type: ignore[no-any-return]


def get_broadcaster(request: Request) -> SSEBroadcaster:
    return request.app.state.broadcaster  # type: ignore[no-any-return]
