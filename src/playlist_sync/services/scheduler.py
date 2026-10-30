"""Periodic synchronization scheduler (RF-17, Phase 6)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from playlist_sync.services.jobs import JobExecutor

logger = logging.getLogger(__name__)


class PeriodicSyncScheduler:
    """Schedules automatic sequential synchronization every N hours."""

    def __init__(
        self,
        job_executor: JobExecutor,
        interval_hours: float = 6.0,
        sleep_fn: Callable[[float], object] | None = None,
    ) -> None:
        self.job_executor = job_executor
        self.interval_hours = interval_hours
        self._sleep_fn = sleep_fn or asyncio.sleep
        self._task: asyncio.Task[None] | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        """Start the periodic synchronization loop as an asyncio background task."""
        if self.interval_hours <= 0:
            logger.info(
                "Periodic synchronization disabled (interval_hours = %s)", self.interval_hours
            )
            return

        if self._is_running:
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Periodic synchronization scheduler started (runs every %.1f hours)",
            self.interval_hours,
        )

    async def stop(self) -> None:
        """Stop the scheduler and cancel background timer."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, TimeoutError):
                pass
            self._task = None
        logger.info("Periodic synchronization scheduler stopped")

    async def _run_loop(self) -> None:
        interval_seconds = self.interval_hours * 3600.0
        while self._is_running:
            try:
                res = self._sleep_fn(interval_seconds)
                if asyncio.iscoroutine(res):
                    await res

                if not self._is_running:
                    break

                if not self.job_executor.is_running:
                    logger.info("Triggering scheduled periodic synchronization of all sources...")
                    await self.job_executor.trigger_sync_all()
                else:
                    logger.info("Skipping scheduled sync: a synchronization is already in progress")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unexpected error in periodic synchronization loop: %s", exc)
                # Brief sleep to avoid rapid failure loops
                await asyncio.sleep(60.0)
