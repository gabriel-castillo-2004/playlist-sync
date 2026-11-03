"""Integration tests for the FastAPI HTTP API, background jobs and SSE (Phase 3)."""

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.api.app import create_app
from playlist_sync.core.models import RemoteItem
from playlist_sync.doctor import SystemDoctor
from playlist_sync.services.jobs import SSEBroadcaster
from tests.integration.test_fake_source import FakeSource


def make_mock_doctor() -> SystemDoctor:
    """Create a mock SystemDoctor that returns instantly without spawning external processes."""
    return SystemDoctor(
        python_version=(3, 12, 3),
        which_fn=lambda _: "/bin/mock",
        run_fn=lambda _: (0, "mock version 1.0"),
        ytdlp_version_fn=lambda: "2026.10.26",
        disk_usage_fn=lambda _: (100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        write_test_fn=lambda _: True,
    )


def test_health_endpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "api_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource(title="Health Source")

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["all_passed"] is True
    assert len(data["checks"]) == 6


def test_sources_crud_endpoints(tmp_path: Path) -> None:
    db_file = tmp_path / "api_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    items = [
        RemoteItem(external_id="v1", title="Song 1", position=1, url="http://v1"),
    ]
    fake = FakeSource(title="API Playlist", items=items)

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    # 1. List initially empty
    resp = client.get("/sources")
    assert resp.status_code == 200
    assert resp.json() == []

    # 2. Add source
    resp = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLvalid"})
    assert resp.status_code == 201
    source_data = resp.json()
    assert source_data["id"] == 1
    assert source_data["title"] == "API Playlist"
    assert source_data["folder_name"] == "API Playlist"

    # 3. List contains 1 source
    resp = client.get("/sources")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 4. Get source detail
    resp = client.get("/sources/1")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == 1
    assert "items" in detail

    # 5. Non-existent source
    resp = client.get("/sources/999")
    assert resp.status_code == 404


def test_sources_error_handling(tmp_path: Path) -> None:
    db_file = tmp_path / "api_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake_private = FakeSource(is_private=True)

    app = create_app(
        repo=repo,
        source_adapter=fake_private,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    # Private source
    resp = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLpriv"})
    assert resp.status_code == 400
    assert "PRIVATE_SOURCE" in resp.text
    assert "privada" in resp.text

    # Invalid URL
    resp = client.post("/sources", json={"url": "ftp://invalid-url.com"})
    assert resp.status_code == 400
    assert "INVALID_URL" in resp.text


def test_sync_and_concurrency_lock_rf11(tmp_path: Path) -> None:
    """Verify RF-11: Mutex lock prevents two concurrent synchronizations, returning 409."""
    db_file = tmp_path / "api_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource(title="Lock Playlist")

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLlock"})

    executor = app.state.job_executor
    assert not executor.is_running

    # Manually acquire the lock to simulate a running job
    async def simulate_held_lock() -> None:
        await executor._lock.acquire()

    asyncio.run(simulate_held_lock())
    assert executor.is_running

    # A concurrent sync request must return 409 Conflict
    resp_conflict = client.post("/sources/1/sync")
    assert resp_conflict.status_code == 409
    assert "Ya hay una sincronización en curso" in resp_conflict.text

    # Sync-all also returns 409 Conflict
    resp_all_conflict = client.post("/sync-all")
    assert resp_all_conflict.status_code == 409

    # Release lock
    executor._lock.release()
    assert not executor.is_running


def test_retry_item_endpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "api_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource(title="Retry Playlist")

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLretry"})
    # Insert an error item
    item = repo.upsert_item(source_id=1, external_id="v_err", title="Err Track", position=1)
    repo.update_item_status(
        item.id, status=item.status, error_code="NETWORK", increment_attempts=True
    )

    # Non-existent item
    resp_missing = client.post("/items/999/retry")
    assert resp_missing.status_code == 404

    # Acquire lock so retry returns 409
    asyncio.run(app.state.job_executor._lock.acquire())
    resp_locked = client.post(f"/items/{item.id}/retry")
    assert resp_locked.status_code == 409
    app.state.job_executor._lock.release()


def test_sse_broadcaster() -> None:
    """Test SSE broadcaster subscription and event emission with strict timeout."""
    broadcaster = SSEBroadcaster()

    async def run_test() -> None:
        gen = broadcaster.subscribe()
        initial_ping = await asyncio.wait_for(anext(gen), timeout=3.0)
        assert "event: ping" in initial_ping

        # Emit an event
        await broadcaster.emit("test_event", {"hello": "world"})
        received = await asyncio.wait_for(anext(gen), timeout=3.0)
        assert "event: test_event" in received
        assert '"hello": "world"' in received

        await gen.aclose()

    asyncio.run(run_test())


def test_rotating_log_creation(tmp_path: Path) -> None:
    """Verify RotatingFileHandler creates the log file."""
    log_file = tmp_path / "test_run.log"
    db_file = tmp_path / "log.sqlite3"
    repo = SQLiteRepo(db_file)
    fake = FakeSource()

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=tmp_path / "music",
        log_file=str(log_file),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)
    client.get("/health")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "playlist_sync" in content


def test_cors_rejects_external_origin_h10(tmp_path: Path) -> None:
    """H-10: Requests from an external Origin must not receive permissive Access-Control-Allow-Origin."""
    db_file = tmp_path / "cors_test.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    fake = FakeSource(title="CORS Playlist")

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "test.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp = client.get(
        "/sources",
        headers={"Origin": "https://sitio-externo.ejemplo"},
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()}

    preflight = client.options(
        "/sources",
        headers={
            "Origin": "https://sitio-externo.ejemplo",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in preflight.headers.keys()}


def test_error_response_hides_technical_detail_and_logs_it(tmp_path: Path) -> None:
    """Audit extra (R3): API error JSON must not expose technical_detail to clients; only log it."""
    db_file = tmp_path / "err_detail.sqlite3"
    music_root = tmp_path / "music"
    log_file = tmp_path / "api_error.log"
    repo = SQLiteRepo(db_file)
    fake_private = FakeSource(is_private=True)

    app = create_app(
        repo=repo,
        source_adapter=fake_private,
        music_root=music_root,
        log_file=str(log_file),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLpriv"})
    assert resp.status_code == 400
    body = resp.json()
    payload = body.get("detail", body)
    assert payload["code"] == "PRIVATE_SOURCE"
    assert "privada" in payload["user_message"]
    assert "technical_detail" not in payload
    assert "Fake private playlist" not in resp.text

    log_content = log_file.read_text(encoding="utf-8")
    assert "Fake private playlist" in log_content


def test_reconcile_endpoints_rf20(tmp_path: Path) -> None:
    """RF-20: REST endpoints POST /reconcile and POST /sources/{id}/reconcile update DB from disk."""
    db_file = tmp_path / "reconcile_api.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    items = [
        RemoteItem(external_id="v1_rec", title="Song 1", position=1, url="http://v1"),
        RemoteItem(external_id="v2_rec", title="Song 2", position=2, url="http://v2"),
    ]
    fake = FakeSource(title="API Reconcile", items=items)

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "reconcile_api.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp_add = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLrec"})
    assert resp_add.status_code == 201
    source_id = resp_add.json()["id"]
    folder_name = resp_add.json()["folder_name"]

    repo.upsert_item(source_id=source_id, external_id="v1_rec", title="Song 1", position=1)
    repo.upsert_item(source_id=source_id, external_id="v2_rec", title="Song 2", position=2)

    src_dir = music_root / folder_name
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "Song 1 [v1_rec].mp3").write_bytes(b"MP3_BYTES_1")

    resp_rec = client.post("/reconcile")
    assert resp_rec.status_code == 200
    body = resp_rec.json()
    assert body["success"] is True
    assert body["reconciled_count"] == 1

    # Add second file on disk and reconcile via source-specific endpoint
    (src_dir / "Song 2 [v2_rec].mp3").write_bytes(b"MP3_BYTES_2")
    resp_src_rec = client.post(f"/sources/{source_id}/reconcile")
    assert resp_src_rec.status_code == 200
    assert resp_src_rec.json()["reconciled_count"] == 1

    detail = client.get(f"/sources/{source_id}").json()
    assert detail["downloaded_count"] == 2
    assert detail["pending_count"] == 0


def test_concurrent_trigger_sync_toctou_h11(tmp_path: Path) -> None:
    """H-11: Two simultaneous trigger_sync calls must not both succeed; one succeeds (200) and one raises AppError (409)."""
    from playlist_sync.core.errors import AppError

    db_file = tmp_path / "toctou.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    items = [RemoteItem(external_id="v1", title="Song 1", position=1, url="http://v1")]
    fake = FakeSource(title="TOCTOU Playlist", items=items)

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "toctou.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp_add = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLtoctou"})
    source_id = resp_add.json()["id"]
    executor = app.state.job_executor

    async def fire_two_simultaneous() -> list[object]:
        results = await asyncio.gather(
            executor.trigger_sync(source_id),
            executor.trigger_sync(source_id),
            return_exceptions=True,
        )
        await executor.wait_idle(timeout=5.0)
        return list(results)

    outcomes = asyncio.run(fire_two_simultaneous())
    successes = [r for r in outcomes if r is True]
    conflicts = [r for r in outcomes if isinstance(r, AppError)]
    assert len(successes) == 1
    assert len(conflicts) == 1


def test_retry_item_lock_guard_resets_attempts_and_200_ok_h12(tmp_path: Path) -> None:
    """H-12: retry_item checks lock before mutating DB, resets attempts to 0, and succeeds with 200 OK."""
    from playlist_sync.core.models import ItemStatus

    db_file = tmp_path / "retry_h12.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    items = [RemoteItem(external_id="v_err", title="Retry Track", position=1, url="http://verr")]
    fake = FakeSource(title="Retry H12 Playlist", items=items)

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "retry_h12.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLretryh12"})
    item = repo.upsert_item(source_id=1, external_id="v_err", title="Retry Track", position=1)
    for _ in range(3):
        repo.update_item_status(
            item.id,
            status=ItemStatus.ERROR,
            error_code="NETWORK",
            error_message="Sin conexión",
            increment_attempts=True,
        )

    item_before = repo.get_item(item.id)
    assert item_before is not None
    assert item_before.attempts == 3
    assert item_before.status == ItemStatus.ERROR

    # 1. While lock is held, /retry returns 409 AND must NOT have cleared status/error in DB
    asyncio.run(app.state.job_executor._lock.acquire())
    resp_locked = client.post(f"/items/{item.id}/retry")
    assert resp_locked.status_code == 409

    item_still_error = repo.get_item(item.id)
    assert item_still_error is not None
    assert item_still_error.status == ItemStatus.ERROR
    assert item_still_error.error_code == "NETWORK"
    assert item_still_error.attempts == 3
    app.state.job_executor._lock.release()

    # 2. When lock is free, /retry returns 200 OK, resets attempts to 0, and downloads the track
    resp_ok = client.post(f"/items/{item.id}/retry")
    assert resp_ok.status_code == 200
    assert resp_ok.json()["success"] is True

    asyncio.run(app.state.job_executor.wait_idle(timeout=5.0))
    item_after = repo.get_item(item.id)
    assert item_after is not None
    assert item_after.status == ItemStatus.DOWNLOADED
    assert item_after.attempts == 1


def test_add_source_populates_pending_items_and_ui_renders_source_error_h09(
    tmp_path: Path,
) -> None:
    """H-09: POST /sources populates initial items as pending (with count) and app.js renders source-level error."""
    db_file = tmp_path / "h09.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    items = [
        RemoteItem(external_id="v1_h09", title="Track 1", position=1, url="http://v1"),
        RemoteItem(external_id="v2_h09", title="Track 2", position=2, url="http://v2"),
    ]
    fake = FakeSource(title="H09 Playlist", items=items)

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        log_file=str(tmp_path / "h09.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    resp = client.post("/sources", json={"url": "https://youtube.com/playlist?list=PLh09"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["pending_count"] == 2
    assert data["last_known_count"] == 2
    assert data["downloaded_count"] == 0

    detail = client.get(f"/sources/{data['id']}").json()
    assert len(detail["items"]) == 2
    assert all(it["status"] == "pending" for it in detail["items"])

    # Verify app.js handles source.status === 'error' with "Hubo un problema" and last_error_message
    app_js = client.get("/app.js").text
    assert "source.status === 'error'" in app_js
    assert "Hubo un problema" in app_js
    assert "source.last_error_message" in app_js


def test_progress_includes_item_index_total_and_sync_all_emits_app_error_h16(
    tmp_path: Path,
) -> None:
    """H-16: Progress includes item_index/total_to_download, UI shows 'Descargando X de Y', and _run_sync_all_task emits AppError.code/user_message."""
    import json

    from playlist_sync.core.models import Progress, SourceKind

    db_file = tmp_path / "h16.sqlite3"
    music_root = tmp_path / "music"
    repo = SQLiteRepo(db_file)
    five_items = [
        RemoteItem(external_id=f"v{i}_h16", title=f"Track {i}", position=i, url=f"http://v{i}")
        for i in range(1, 6)
    ]
    fake = FakeSource(title="H16 Playlist", items=five_items)
    broadcaster = SSEBroadcaster()

    app = create_app(
        repo=repo,
        source_adapter=fake,
        music_root=music_root,
        broadcaster=broadcaster,
        log_file=str(tmp_path / "h16.log"),
    )
    app.state.doctor = make_mock_doctor()
    client = TestClient(app)

    # 1. Verify Progress model has item_index and total_to_download
    p = Progress(status="downloading", item_index=2, total_to_download=5)
    assert p.item_index == 2
    assert p.total_to_download == 5

    # 2. Verify sync_all emits item_index / total_to_download during download and err.code / err.user_message on AppError
    src = repo.add_source(
        kind=SourceKind.YT_PLAYLIST,
        url="https://youtube.com/playlist?list=PLh16",
        title="H16 Private Source",
    )
    observed_indices: list[tuple[int | None, int | None]] = []
    from playlist_sync.services.sync import sync_source_service

    sync_source_service(
        repo=repo,
        source_adapter=fake,
        source_id=src.id,
        music_root=music_root,
        on_progress=lambda prog: observed_indices.append((prog.item_index, prog.total_to_download)),
        min_free_mb=1,
    )
    assert (2, 5) in observed_indices
    assert (5, 5) in observed_indices

    fake.is_private = True

    async def run_sync_all_and_collect() -> list[str]:
        gen = broadcaster.subscribe()
        # Consume initial ping
        await asyncio.wait_for(anext(gen), timeout=3.0)
        await app.state.job_executor.trigger_sync_all()
        await app.state.job_executor.wait_idle(timeout=5.0)

        events: list[str] = []
        while True:
            try:
                ev = await asyncio.wait_for(anext(gen), timeout=0.2)
                events.append(ev)
            except TimeoutError:
                break
        await gen.aclose()
        return events

    emitted = asyncio.run(run_sync_all_and_collect())
    failed_events = [e for e in emitted if "event: sync_failed" in e]
    assert len(failed_events) == 1
    data_line = [line for line in failed_events[0].splitlines() if line.startswith("data: ")][0]
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["source_id"] == src.id
    assert payload["error_code"] == "PRIVATE_SOURCE"
    assert "privada" in payload["message"]
    assert "Fake private playlist" not in payload["message"]

    # 3. Verify app.js formats 'Descargando ${data.item_index} de ${data.total_to_download}'
    app_js = client.get("/app.js").text
    assert "item_index" in app_js
    assert "total_to_download" in app_js
    assert "Descargando ${data.item_index} de ${data.total_to_download}" in app_js
