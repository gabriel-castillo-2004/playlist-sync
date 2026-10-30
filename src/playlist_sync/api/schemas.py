"""Pydantic API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    url: str = Field(..., description="URL of the YouTube playlist or podcast")


class ItemResponse(BaseModel):
    id: int
    source_id: int
    external_id: str
    title: str
    position: int
    published_at: datetime | None = None
    status: str
    error_code: str | None = None
    error_message: str | None = None
    attempts: int
    file_path: str | None = None
    downloaded_at: datetime | None = None
    removed_remote: bool = False


class SourceResponse(BaseModel):
    id: int
    kind: str
    url: str
    title: str
    cover_url: str | None = None
    folder_name: str
    status: str
    last_sync_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_known_count: int = 0
    created_at: datetime
    downloaded_count: int = 0
    pending_count: int = 0
    error_count: int = 0


class SourceDetailResponse(SourceResponse):
    items: list[ItemResponse] = []


class ActionResponse(BaseModel):
    success: bool
    message: str
    source_id: int | None = None


class ErrorResponse(BaseModel):
    code: str
    user_message: str
    technical_detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    all_passed: bool
    checks: list[dict[str, Any]]


class PodcastSearchItemResponse(BaseModel):
    title: str
    artist: str
    feed_url: str
    cover_url: str | None = None
    track_count: int | None = None
    genre: str | None = None
