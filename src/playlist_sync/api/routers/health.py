"""System health and diagnostic API router (RF-15)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from playlist_sync.api.schemas import HealthResponse
from playlist_sync.doctor import SystemDoctor

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_system_health(request: Request) -> HealthResponse:
    """Run system diagnostics and return component status."""
    music_root: Path = request.app.state.music_root
    min_disk_free_mb: int = request.app.state.min_disk_free_mb

    doctor: SystemDoctor = getattr(request.app.state, "doctor", None) or SystemDoctor()
    results = doctor.run_all(target_dir=music_root, min_mb=min_disk_free_mb)

    all_passed = all(r.passed for r in results if r.critical)
    serialized_checks = [
        {
            "name": r.name,
            "passed": r.passed,
            "critical": r.critical,
            "message": r.message,
            "recommendation": r.recommendation,
        }
        for r in results
    ]

    return HealthResponse(
        status="ok" if all_passed else "degraded",
        all_passed=all_passed,
        checks=serialized_checks,
    )
