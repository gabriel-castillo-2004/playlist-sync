"""Routes for global sync orchestration and item retries."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from playlist_sync.api.deps import get_job_executor
from playlist_sync.api.schemas import ActionResponse
from playlist_sync.core.errors import AppError, ErrorCode
from playlist_sync.services.jobs import JobExecutor

router = APIRouter(tags=["sync"])
logger = logging.getLogger(__name__)


@router.post("/sync-all", response_model=ActionResponse)
async def sync_all_sources(
    job_executor: Annotated[JobExecutor, Depends(get_job_executor)],
) -> ActionResponse:
    """Trigger sequential synchronization of all sources in background."""
    try:
        await job_executor.trigger_sync_all()
        return ActionResponse(
            success=True,
            message="Sincronización global iniciada en segundo plano.",
        )
    except AppError as err:
        if err.technical_detail:
            logger.warning(
                "Sync-all conflict [%s]: %s | technical_detail=%s",
                err.code,
                err.user_message,
                err.technical_detail,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": err.code,
                "user_message": err.user_message,
            },
        ) from err


@router.post("/items/{item_id}/retry", response_model=ActionResponse)
async def retry_item(
    item_id: int,
    job_executor: Annotated[JobExecutor, Depends(get_job_executor)],
) -> ActionResponse:
    """Reset attempts on a failed item and trigger sync."""
    try:
        await job_executor.retry_item(item_id)
        return ActionResponse(
            success=True,
            message="Reintento programado en segundo plano.",
        )
    except AppError as err:
        if err.technical_detail:
            logger.warning(
                "Retry item failed [%s]: %s | technical_detail=%s",
                err.code,
                err.user_message,
                err.technical_detail,
            )
        code = (
            status.HTTP_404_NOT_FOUND
            if err.code == ErrorCode.SOURCE_NOT_FOUND
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=code,
            detail={
                "code": err.code,
                "user_message": err.user_message,
            },
        ) from err
