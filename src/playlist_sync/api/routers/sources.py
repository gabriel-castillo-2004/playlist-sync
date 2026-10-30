"""Routes for managing and inspecting sources."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.api.deps import get_job_executor, get_repo, get_source_adapter
from playlist_sync.api.schemas import (
    ActionResponse,
    ItemResponse,
    SourceCreate,
    SourceDetailResponse,
    SourceResponse,
)
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.core.models import ItemStatus, Source, SourceRecord
from playlist_sync.services.jobs import JobExecutor
from playlist_sync.services.sync import add_source_service

router = APIRouter(prefix="/sources", tags=["sources"])


def _source_to_response(repo: SQLiteRepo, src: SourceRecord) -> SourceResponse:
    items = repo.get_items_by_source(src.id)
    downloaded = sum(1 for it in items if it.status == ItemStatus.DOWNLOADED)
    pending = sum(1 for it in items if it.status in (ItemStatus.PENDING, ItemStatus.DOWNLOADING))
    errors = sum(1 for it in items if it.status == ItemStatus.ERROR)

    return SourceResponse(
        id=src.id,
        kind=src.kind.value,
        url=src.url,
        title=src.title,
        cover_url=src.cover_url,
        folder_name=src.folder_name,
        status=src.status.value,
        last_sync_at=src.last_sync_at,
        last_error_code=src.last_error_code,
        last_error_message=src.last_error_message,
        last_known_count=src.last_known_count,
        created_at=src.created_at,
        downloaded_count=downloaded,
        pending_count=pending,
        error_count=errors,
    )


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    repo: Annotated[SQLiteRepo, Depends(get_repo)],
    source_adapter: Annotated[Source, Depends(get_source_adapter)],
) -> SourceResponse:
    """Register a new source URL."""
    try:
        source = add_source_service(repo, source_adapter, payload.url)
        return _source_to_response(repo, source)
    except AppError as err:
        status_code = status.HTTP_400_BAD_REQUEST
        if err.code in (ErrorCode.PRIVATE_SOURCE, ErrorCode.INVALID_URL):
            status_code = status.HTTP_400_BAD_REQUEST
        elif err.code == ErrorCode.SOURCE_NOT_FOUND:
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": err.code,
                "user_message": err.user_message,
                "technical_detail": err.technical_detail,
            },
        ) from err


@router.get("", response_model=list[SourceResponse])
def list_sources(repo: Annotated[SQLiteRepo, Depends(get_repo)]) -> list[SourceResponse]:
    """List all tracked sources."""
    sources = repo.list_sources()
    return [_source_to_response(repo, s) for s in sources]


@router.get("/{source_id}", response_model=SourceDetailResponse)
def get_source_detail(
    source_id: int,
    repo: Annotated[SQLiteRepo, Depends(get_repo)],
) -> SourceDetailResponse:
    """Retrieve details and track list for a specific source."""
    source = repo.get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ErrorCode.SOURCE_NOT_FOUND,
                "user_message": "No se encontró la fuente solicitada.",
                "technical_detail": f"Source {source_id} not found",
            },
        )

    base = _source_to_response(repo, source)
    items_db = repo.get_items_by_source(source.id)
    item_responses = [
        ItemResponse(
            id=it.id,
            source_id=it.source_id,
            external_id=it.external_id,
            title=it.title,
            position=it.position,
            published_at=it.published_at,
            status=it.status.value,
            error_code=it.error_code,
            error_message=it.error_message,
            attempts=it.attempts,
            file_path=it.file_path,
            downloaded_at=it.downloaded_at,
            removed_remote=it.removed_remote,
        )
        for it in items_db
    ]

    return SourceDetailResponse(
        **base.model_dump(),
        items=item_responses,
    )


@router.post("/{source_id}/sync", response_model=ActionResponse)
async def sync_source(
    source_id: int,
    repo: Annotated[SQLiteRepo, Depends(get_repo)],
    job_executor: Annotated[JobExecutor, Depends(get_job_executor)],
) -> ActionResponse:
    """Trigger background synchronization for a specific source."""
    source = repo.get_source(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ErrorCode.SOURCE_NOT_FOUND,
                "user_message": "No se encontró la fuente solicitada.",
                "technical_detail": f"Source {source_id} not found",
            },
        )

    try:
        await job_executor.trigger_sync(source_id)
        return ActionResponse(
            success=True,
            message="Sincronización iniciada en segundo plano.",
            source_id=source_id,
        )
    except AppError as err:
        # Mutex lock conflict RF-11
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": err.code,
                "user_message": err.user_message,
                "technical_detail": err.technical_detail,
            },
        ) from err
