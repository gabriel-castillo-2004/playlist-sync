"""Integration tests for export/migration of SQLite database to JSON (Phase 6)."""

from __future__ import annotations

import json
from pathlib import Path

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.models import RemoteItem, SourceKind
from playlist_sync.services.migration import export_sources_to_json, import_sources_from_json
from tests.integration.test_fake_source import FakeSource


def test_export_and_import_sources_json(tmp_path: Path) -> None:
    # Machine A: original database
    db_a = tmp_path / "machine_a.sqlite3"
    repo_a = SQLiteRepo(db_a)

    repo_a.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PLa",
        title="Playlist Alpha",
        cover_url="https://example.com/a.jpg",
    )
    repo_a.add_source(
        kind=SourceKind.RSS_PODCAST,
        url="https://feeds.example.com/podcast.xml",
        title="Podcast Beta",
        cover_url="https://example.com/b.jpg",
    )

    # Export to sources.json
    export_json = tmp_path / "sources.json"
    result_path = export_sources_to_json(repo_a, export_json)
    assert result_path.exists()

    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["total_sources"] == 2
    assert len(data["sources"]) == 2
    assert data["sources"][0]["title"] == "Playlist Alpha"
    assert data["sources"][1]["kind"] == "rss_podcast"

    # Machine B: fresh database importing sources.json
    db_b = tmp_path / "machine_b.sqlite3"
    repo_b = SQLiteRepo(db_b)
    assert repo_b.list_sources() == []

    fake_source = FakeSource(
        title="Imported Source",
        items=[RemoteItem(external_id="v1", title="S1", position=1, url="http://v1")],
    )

    import_summary = import_sources_from_json(repo_b, fake_source, export_json)
    assert import_summary["imported"] == 2
    assert import_summary["skipped"] == 0

    sources_b = repo_b.list_sources()
    assert len(sources_b) == 2
    urls_b = {s.url for s in sources_b}
    assert "https://youtube.com/playlist?list=PLa" in urls_b
    assert "https://feeds.example.com/podcast.xml" in urls_b

    # Second import of same file: idempotent (skips already tracked URLs)
    re_import = import_sources_from_json(repo_b, fake_source, export_json)
    assert re_import["imported"] == 0
    assert re_import["skipped"] == 2
