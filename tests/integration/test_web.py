"""Integration tests for the Web frontend adapter and static assets (Phase 4)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.api.app import create_app
from playlist_sync.core.models import RemoteItem
from playlist_sync.doctor import SystemDoctor
from tests.integration.test_fake_source import FakeSource


def make_mock_doctor() -> SystemDoctor:
    return SystemDoctor(
        python_version=(3, 12, 3),
        which_fn=lambda _: "/bin/mock",
        run_fn=lambda _: (0, "mock version 1.0"),
        ytdlp_version_fn=lambda: "2026.10.26",
        disk_usage_fn=lambda _: (100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        write_test_fn=lambda _: True,
    )


def test_web_root_serves_index_html(tmp_path: Path) -> None:
    """Verify GET / serves index.html with appropriate title and scripts."""
    db_file = tmp_path / "web_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource()

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "web.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Mi Música" in resp.text
    assert "/app.js" in resp.text
    assert "/styles.css" in resp.text


def test_web_static_assets_served(tmp_path: Path) -> None:
    """Verify static styles, scripts, manifest, and icons are accessible."""
    db_file = tmp_path / "web_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource()

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "web.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    # 1. styles.css
    resp_css = client.get("/styles.css")
    assert resp_css.status_code == 200
    assert "text/css" in resp_css.headers["content-type"]
    assert "prefers-color-scheme" in resp_css.text

    # 2. style.css alias
    resp_alias = client.get("/style.css")
    assert resp_alias.status_code == 200
    assert "text/css" in resp_alias.headers["content-type"]

    # 3. app.js
    resp_js = client.get("/app.js")
    assert resp_js.status_code == 200
    assert "javascript" in resp_js.headers["content-type"]
    assert "EventSource" in resp_js.text
    assert "startContingencyPolling" in resp_js.text

    # 4. manifest.webmanifest
    resp_manifest = client.get("/manifest.webmanifest")
    assert resp_manifest.status_code == 200
    manifest_data = json.loads(resp_manifest.text)
    assert manifest_data["name"] == "Playlist Sync"
    assert manifest_data["display"] == "standalone"

    # 5. icons
    resp_svg = client.get("/icons/icon.svg")
    assert resp_svg.status_code == 200
    assert "image/svg+xml" in resp_svg.headers["content-type"]

    resp_png = client.get("/icons/icon-192.png")
    assert resp_png.status_code == 200
    assert "image/png" in resp_png.headers["content-type"]


def test_cover_endpoint_behavior(tmp_path: Path) -> None:
    """Verify /covers/{source_id} serves local cover, redirects remote, or returns SVG fallback."""
    db_file = tmp_path / "web_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    items = [RemoteItem(external_id="v1", title="Song 1", position=1, url="http://v1")]
    fake = FakeSource(title="Cover Playlist", items=items)

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "web.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    # 1. Non-existent source -> 404
    resp_404 = client.get("/covers/999")
    assert resp_404.status_code == 404

    # 2. Register source with remote cover_url
    resp_add = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLcover"})
    assert resp_add.status_code == 201
    source_id = resp_add.json()["id"]

    # Remote redirect (follow_redirects=False)
    resp_redirect = client.get(f"/covers/{source_id}", follow_redirects=False)
    assert resp_redirect.status_code == 302
    assert resp_redirect.headers["location"] == "http://fake.url/cover.jpg"

    # 3. When local cover.jpg exists on disk, it should return FileResponse
    source_folder = music_root / resp_add.json()["folder_name"]
    source_folder.mkdir(parents=True, exist_ok=True)
    local_cover = source_folder / "cover.jpg"
    local_cover.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)  # mock jpeg bytes

    resp_local = client.get(f"/covers/{source_id}")
    assert resp_local.status_code == 200
    assert "image/jpeg" in resp_local.headers["content-type"]
