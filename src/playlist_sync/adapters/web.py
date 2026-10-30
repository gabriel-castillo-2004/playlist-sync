"""Web adapter for serving frontend assets and cover artwork."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles

from playlist_sync.adapters.repo import SQLiteRepo

logger = logging.getLogger(__name__)

DEFAULT_COVER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <rect width="100" height="100" fill="#2d3748" rx="8"/>
  <path d="M40 30 v30 a10 10 0 1 0 10 10 v-25 h20 v-15 z" fill="#e2e8f0"/>
</svg>"""


def mount_web_adapter(
    app: FastAPI,
    web_dir: Path | None = None,
    music_root: Path | None = None,
) -> None:
    """Mount static file serving and cover image endpoints onto the FastAPI app."""
    target_web_dir = web_dir or (Path(__file__).parent.parent / "web")

    # 1. Endpoint for source cover art
    @app.get("/covers/{source_id}", tags=["web"])
    def get_source_cover(source_id: int, request: Request) -> Response:
        repo: SQLiteRepo = request.app.state.repo
        source = repo.get_source(source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fuente no encontrada",
            )

        resolved_music_root = music_root or request.app.state.music_root
        local_cover = Path(resolved_music_root) / source.folder_name / "cover.jpg"
        if local_cover.is_file():
            return FileResponse(local_cover, media_type="image/jpeg")

        if source.cover_url and source.cover_url.startswith(("http://", "https://")):
            return RedirectResponse(url=source.cover_url, status_code=status.HTTP_302_FOUND)

        return Response(content=DEFAULT_COVER_SVG, media_type="image/svg+xml")

    # 2. Compatibility alias: /style.css -> /styles.css
    @app.get("/style.css", include_in_schema=False)
    def style_css_alias() -> Response:
        style_path = target_web_dir / "styles.css"
        if style_path.is_file():
            return FileResponse(style_path, media_type="text/css")
        alt_path = target_web_dir / "style.css"
        if alt_path.is_file():
            return FileResponse(alt_path, media_type="text/css")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # 3. Mount static web directory at root '/'
    if target_web_dir.is_dir() and (target_web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(target_web_dir), html=True), name="web")
        logger.info("Mounted web frontend from %s", target_web_dir)
    else:
        logger.warning(
            "Web frontend directory %s not found or missing index.html; static files not mounted",
            target_web_dir,
        )
