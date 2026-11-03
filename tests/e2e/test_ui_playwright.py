"""End-to-end (E2E) tests for Playlist Sync (Phase 7 / Stage R6 — H-19)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from mutagen.id3 import ID3

from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.api.app import create_app
from playlist_sync.core.models import ItemStatus, RemoteItem
from playlist_sync.doctor import SystemDoctor
from tests.integration.test_fake_source import FakeSource


def _make_mock_doctor() -> SystemDoctor:
    return SystemDoctor(
        python_version=(3, 12, 3),
        which_fn=lambda _: "/bin/mock",
        run_fn=lambda _: (0, "mock version 1.0"),
        ytdlp_version_fn=lambda: "2026.10.26",
        disk_usage_fn=lambda _: (100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        write_test_fn=lambda _: True,
    )


def test_e2e_full_lifecycle_add_sync_m3u8_and_second_run_idempotency(tmp_path: Path) -> None:
    """H-19: Full E2E flow with FakeSource (add -> sync -> files & .m3u8 -> 2nd run idempotent -> reconcile)."""
    db_file = tmp_path / "e2e.sqlite3"
    music_root = tmp_path / "music_root"
    repo = SQLiteRepo(db_file)
    library = LocalLibrary(music_root)

    remote_tracks = [
        RemoteItem(
            external_id="e2eTrack001",
            title="Artista Uno - Cancion Uno",
            position=1,
            url="https://youtube.com/watch?v=e2eTrack001",
            artist="Artista Uno",
        ),
        RemoteItem(
            external_id="e2eTrack002",
            title="Artista Dos - Cancion Dos",
            position=2,
            url="https://youtube.com/watch?v=e2eTrack002",
            artist="Artista Dos",
        ),
    ]
    fake_source = FakeSource(title="Lista E2E Prueba", items=remote_tracks)

    app = create_app(
        repo=repo,
        source_adapter=fake_source,
        music_root=music_root,
        library=library,
        min_disk_free_mb=1,
        log_file=str(tmp_path / "e2e.log"),
    )
    app.state.doctor = _make_mock_doctor()
    client = TestClient(app)

    # 1. Health check endpoint responds 200 OK
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "ok"

    # 2. Add source via REST API -> populates initial pending items (H-09)
    resp_add = client.post(
        "/sources",
        json={"url": "https://music.youtube.com/playlist?list=PL_E2E_01", "sync_now": False},
    )
    assert resp_add.status_code == 201
    source_data = resp_add.json()
    source_id = source_data["id"]
    folder_name = source_data["folder_name"]
    assert source_data["pending_count"] == 2
    assert source_data["downloaded_count"] == 0

    # 3. First synchronization run -> downloads all tracks, writes ID3 tags and .m3u8
    resp_sync1 = client.post(f"/sources/{source_id}/sync")
    assert resp_sync1.status_code == 200

    import asyncio

    asyncio.run(app.state.job_executor.wait_idle(timeout=5.0))

    resp_detail1 = client.get(f"/sources/{source_id}")
    assert resp_detail1.status_code == 200
    detail1 = resp_detail1.json()
    assert detail1["downloaded_count"] == 2
    assert detail1["pending_count"] == 0
    assert detail1["error_count"] == 0

    source_dir = music_root / folder_name
    assert source_dir.is_dir()

    mp3_files = sorted(source_dir.glob("*.mp3"))
    assert len(mp3_files) == 2
    assert any(p.name.endswith("[e2eTrack001].mp3") for p in mp3_files)
    assert any(p.name.endswith("[e2eTrack002].mp3") for p in mp3_files)

    # Verify ID3v2.3 tags on downloaded files
    for mp3_file in mp3_files:
        tags = ID3(str(mp3_file))
        assert "TIT2" in tags
        assert "TPE1" in tags
        assert "TALB" in tags and str(tags["TALB"].text[0]) == "Lista E2E Prueba"

    # Verify relative UTF-8 .m3u8 playlist
    m3u8_file = source_dir / f"{folder_name}.m3u8"
    assert m3u8_file.is_file()
    m3u8_lines = [
        line.strip()
        for line in m3u8_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(m3u8_lines) == 2
    assert m3u8_lines[0].endswith("[e2eTrack001].mp3")
    assert m3u8_lines[1].endswith("[e2eTrack002].mp3")
    assert all("/" not in line and "\\" not in line for line in m3u8_lines)

    mtimes_before = {p.name: p.stat().st_mtime_ns for p in mp3_files}

    # 4. Second synchronization run -> strictly idempotent (no files re-downloaded or modified)
    resp_sync2 = client.post(f"/sources/{source_id}/sync")
    assert resp_sync2.status_code == 200
    asyncio.run(app.state.job_executor.wait_idle(timeout=5.0))

    mtimes_after = {p.name: p.stat().st_mtime_ns for p in sorted(source_dir.glob("*.mp3"))}
    assert mtimes_before == mtimes_after

    # 5. Reconcile endpoint (RF-20) -> restores a pending item if its MP3 already exists on disk
    items_in_db = repo.get_items_by_source(source_id)
    repo.update_item_status(items_in_db[0].id, ItemStatus.PENDING)
    resp_rec = client.post("/reconcile")
    assert resp_rec.status_code == 200
    assert resp_rec.json()["reconciled_count"] == 1


def test_e2e_ui_rendering_and_js_integrity(tmp_path: Path) -> None:
    """Verify UI HTML, CSS, and JS syntax/structure and key user-facing elements."""
    db_file = tmp_path / "ui_e2e.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake_source = FakeSource(title="UI Test Playlist")

    app = create_app(
        repo=repo,
        source_adapter=fake_source,
        music_root=music_root,
        min_disk_free_mb=1,
        log_file=str(tmp_path / "ui_e2e.log"),
    )
    app.state.doctor = _make_mock_doctor()
    client = TestClient(app)

    # 1. Verify HTML shell and accessibility controls
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    html = html_resp.text
    assert 'id="btn-sync-all"' in html
    assert 'id="btn-reconcile"' in html
    assert 'id="add-source-form"' in html
    assert '<button id="system-health-pill"' in html
    assert 'id="health-modal"' in html

    # 2. Verify app.js syntax is 100% valid JavaScript using Node's syntax checker
    web_dir = Path(__file__).resolve().parent.parent.parent / "src" / "playlist_sync" / "web"
    app_js_path = web_dir / "app.js"
    proc = subprocess.run(
        ["node", "--check", str(app_js_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"JavaScript syntax error in app.js: {proc.stderr}"
