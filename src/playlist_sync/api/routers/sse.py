"""Server-Sent Events (SSE) router for live progress updates (RF-10)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from playlist_sync.api.deps import get_broadcaster
from playlist_sync.services.jobs import SSEBroadcaster

router = APIRouter(tags=["events"])


@router.get("/events")
async def events_stream(
    broadcaster: Annotated[SSEBroadcaster, Depends(get_broadcaster)],
) -> StreamingResponse:
    """Stream live synchronization and progress events via Server-Sent Events."""
    return StreamingResponse(
        broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
