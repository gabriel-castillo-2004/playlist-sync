"""Export and import utilities for migrating sources via JSON across machines (Phase 6)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.models import Source, SourceKind
from playlist_sync.services.sync import add_source_service

logger = logging.getLogger(__name__)


def export_sources_to_json(
    repo: SQLiteRepo,
    output_file: Path | str = "sources.json",
) -> Path:
    """Export tracked sources to a portable JSON file."""
    sources = repo.list_sources()
    data: dict[str, Any] = {
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "total_sources": len(sources),
        "sources": [
            {
                "kind": s.kind.value,
                "url": s.url,
                "title": s.title,
                "cover_url": s.cover_url,
                "folder_name": s.folder_name,
            }
            for s in sources
        ],
    }

    target_path = Path(output_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Exported %d sources to %s", len(sources), target_path)
    return target_path


def import_sources_from_json(
    repo: SQLiteRepo,
    source_adapter: Source | None = None,
    json_file: Path | str = "sources.json",
) -> dict[str, int]:
    """Import sources from a JSON file into the local database."""
    source_path = Path(json_file)
    if not source_path.exists():
        raise FileNotFoundError(f"Archivo de fuentes no encontrado: {source_path}")

    raw_data = json.loads(source_path.read_text(encoding="utf-8"))
    sources_data = raw_data.get("sources", [])

    imported_count = 0
    skipped_count = 0

    for item in sources_data:
        url = item.get("url")
        if not url:
            continue

        existing = repo.get_source_by_url(url)
        if existing:
            skipped_count += 1
            continue

        kind_str = item.get("kind", SourceKind.YT_PLAYLIST.value)
        try:
            kind = SourceKind(kind_str)
        except ValueError:
            kind = SourceKind.YT_PLAYLIST

        title = item.get("title") or "Fuente Importada"
        cover_url = item.get("cover_url")
        folder_name = item.get("folder_name")

        if source_adapter is not None:
            try:
                # If adapter is available, attempt inspect to refresh metadata
                add_source_service(repo, source_adapter, url)
                imported_count += 1
                continue
            except Exception as exc:
                logger.warning(
                    "Could not inspect imported URL %s (%s); inserting directly", url, exc
                )

        # Direct database insertion
        repo.add_source(
            kind=kind,
            url=url,
            title=title,
            cover_url=cover_url,
            folder_name=folder_name,
        )
        imported_count += 1

    logger.info("Import finished: %d imported, %d skipped", imported_count, skipped_count)
    return {"imported": imported_count, "skipped": skipped_count}
