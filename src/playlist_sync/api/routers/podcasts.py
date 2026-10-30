"""Routes for podcast search and discovery (RF-13)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from playlist_sync.adapters.itunes_search import search_itunes_podcasts
from playlist_sync.api.schemas import PodcastSearchItemResponse

router = APIRouter(prefix="/podcasts", tags=["podcasts"])


@router.get("/search", response_model=list[PodcastSearchItemResponse])
def search_podcasts(
    q: str = Query(..., min_length=1, description="Podcast search term"),
    limit: int = Query(8, ge=1, le=20),
) -> list[PodcastSearchItemResponse]:
    """Search for podcasts by title or author using the iTunes Search API."""
    results = search_itunes_podcasts(q, limit=limit)
    return [
        PodcastSearchItemResponse(
            title=r.title,
            artist=r.artist,
            feed_url=r.feed_url,
            cover_url=r.cover_url,
            track_count=r.track_count,
            genre=r.genre,
        )
        for r in results
    ]
