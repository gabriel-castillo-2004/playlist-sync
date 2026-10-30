"""Unit tests for the periodic synchronization scheduler (RF-17)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from playlist_sync.adapters.library import LocalLibrary
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.services.jobs import JobExecutor, SSEBroadcaster
from playlist_sync.services.scheduler import PeriodicSyncScheduler
from tests.integration.test_fake_source import FakeSource


def test_scheduler_disabled_when_zero(tmp_path: Path) -> None:
    repo = SQLiteRepo(tmp_path / "sched.sqlite3")
    fake = FakeSource()
    executor = JobExecutor(
        repo=repo,
        source_adapter=fake,
        music_root=tmp_path / "music",
        library=LocalLibrary(tmp_path / "music"),
        broadcaster=SSEBroadcaster(),
    )
    scheduler = PeriodicSyncScheduler(executor, interval_hours=0)
    scheduler.start()
    assert not scheduler.is_running


def test_scheduler_start_and_trigger(tmp_path: Path) -> None:
    repo = SQLiteRepo(tmp_path / "sched2.sqlite3")
    fake = FakeSource(title="Sched Test")
    repo.add_source(
        kind=fake.inspect("http://fake").kind,
        url="http://fake",
        title="Sched Test",
    )
    executor = JobExecutor(
        repo=repo,
        source_adapter=fake,
        music_root=tmp_path / "music",
        library=LocalLibrary(tmp_path / "music"),
        broadcaster=SSEBroadcaster(),
    )

    triggered = False

    async def mock_sleep(seconds: float) -> None:
        nonlocal triggered
        triggered = True
        await asyncio.sleep(0.01)

    scheduler = PeriodicSyncScheduler(
        executor,
        interval_hours=1.0,
        sleep_fn=mock_sleep,
    )

    async def run_test() -> None:
        scheduler.start()
        assert scheduler.is_running
        # Allow loop to tick once
        await asyncio.sleep(0.05)
        await scheduler.stop()
        assert not scheduler.is_running
        assert triggered

    asyncio.run(run_test())
