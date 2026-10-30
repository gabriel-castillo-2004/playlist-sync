"""Unit tests for the system health doctor (RF-15)."""

import sys
from pathlib import Path

import pytest

from playlist_sync.doctor import CheckResult, SystemDoctor
from playlist_sync.main import main


def test_doctor_all_passed(tmp_path: Path) -> None:
    """Test doctor when all tools and prerequisites are satisfied."""
    doctor = SystemDoctor(
        python_version=(3, 12, 3),
        which_fn=lambda cmd: f"/usr/bin/{cmd}",
        run_fn=lambda cmd: (0, f"{cmd[0]} version 1.0"),
        ytdlp_version_fn=lambda: "2025.02.19",
        disk_usage_fn=lambda path: (100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
        write_test_fn=lambda path: True,
    )
    results = doctor.run_all(target_dir=tmp_path)
    assert len(results) == 6
    assert all(r.passed for r in results)
    assert all(r.critical or r.name.startswith("Runtime") for r in results)


def test_doctor_python_too_old() -> None:
    """Test doctor when Python version is below 3.12."""
    doctor = SystemDoctor(python_version=(3, 10, 12))
    res = doctor.check_python()
    assert not res.passed
    assert res.critical
    assert "3.10.12" in res.message
    assert res.recommendation is not None
    assert "3.12" in res.recommendation


def test_doctor_ffmpeg_missing() -> None:
    """Test doctor when ffmpeg is not found."""
    doctor = SystemDoctor(which_fn=lambda _: None)
    res = doctor.check_ffmpeg()
    assert not res.passed
    assert res.critical
    assert "No se encontró ffmpeg" in res.message
    assert "apt install ffmpeg" in (res.recommendation or "")


def test_doctor_ffmpeg_execution_error() -> None:
    """Test doctor when ffmpeg is present but exits with error."""
    doctor = SystemDoctor(
        which_fn=lambda _: "/bin/ffmpeg",
        run_fn=lambda _: (1, "shared library missing"),
    )
    res = doctor.check_ffmpeg()
    assert not res.passed
    assert res.critical
    assert "devolvió un error" in res.message


def test_doctor_js_runtime_with_deno() -> None:
    """Test doctor detecting Deno."""
    doctor = SystemDoctor(
        which_fn=lambda cmd: "/bin/deno" if cmd == "deno" else None,
        run_fn=lambda cmd: (0, "deno 2.1.0"),
    )
    res = doctor.check_js_runtime()
    assert res.passed
    assert not res.critical
    assert "deno 2.1.0" in res.message


def test_doctor_js_runtime_with_node() -> None:
    """Test doctor detecting Node when Deno is missing."""
    doctor = SystemDoctor(
        which_fn=lambda cmd: "/bin/node" if cmd == "node" else None,
        run_fn=lambda cmd: (0, "v20.10.0"),
    )
    res = doctor.check_js_runtime()
    assert res.passed
    assert not res.critical
    assert "Node.js" in res.message


def test_doctor_js_runtime_missing() -> None:
    """Test doctor when neither Deno nor Node is present (non-critical)."""
    doctor = SystemDoctor(which_fn=lambda _: None)
    res = doctor.check_js_runtime()
    assert not res.passed
    assert not res.critical
    assert "No se encontró Deno ni Node.js" in res.message
    assert res.recommendation is not None


def test_doctor_ytdlp_missing() -> None:
    """Test doctor when yt-dlp is not installed."""
    doctor = SystemDoctor(ytdlp_version_fn=lambda: None)
    res = doctor.check_ytdlp()
    assert not res.passed
    assert res.critical
    assert "no está instalado" in res.message
    assert "pip install yt-dlp" in (res.recommendation or "")


def test_doctor_disk_space_insufficient(tmp_path: Path) -> None:
    """Test doctor when free disk space is below required threshold."""
    # 500 MB free, min required 1024 MB
    doctor = SystemDoctor(
        disk_usage_fn=lambda path: (100 * 1024**3, 99 * 1024**3, 500 * 1024**2),
    )
    res = doctor.check_disk_space(tmp_path, min_mb=1024)
    assert not res.passed
    assert res.critical
    assert "500 MB libres" in res.message


def test_doctor_disk_space_error(tmp_path: Path) -> None:
    """Test doctor when disk usage check raises exception."""

    def raise_err(_: Path) -> tuple[int, int, int]:
        raise OSError("Disk check failed")

    doctor = SystemDoctor(disk_usage_fn=raise_err)
    res = doctor.check_disk_space(tmp_path)
    assert not res.passed
    assert "No se pudo consultar el espacio en disco" in res.message


def test_doctor_write_permissions_denied(tmp_path: Path) -> None:
    """Test doctor when directory write check fails."""
    doctor = SystemDoctor(write_test_fn=lambda _: False)
    res = doctor.check_write_permissions(tmp_path)
    assert not res.passed
    assert res.critical
    assert "No se tienen permisos de escritura" in res.message


def test_run_doctor_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test run_doctor function output and return code."""
    from playlist_sync.doctor import run_doctor

    # Mock SystemDoctor to pass all checks
    monkeypatch.setattr(
        "playlist_sync.doctor.SystemDoctor.run_all",
        lambda self, target_dir=None, min_mb=1024: [
            CheckResult(name="Python", passed=True, critical=True, message="OK"),
            CheckResult(
                name="Deno", passed=False, critical=False, message="Warn", recommendation="install"
            ),
        ],
    )
    passed = run_doctor(target_dir=tmp_path)
    assert passed
    captured = capsys.readouterr().out
    assert "Diagnostico de Salud" in captured
    assert "cumple con los requisitos" in captured


def test_run_doctor_cli_critical_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test run_doctor function when a critical check fails."""
    from playlist_sync.doctor import run_doctor

    monkeypatch.setattr(
        "playlist_sync.doctor.SystemDoctor.run_all",
        lambda self, target_dir=None, min_mb=1024: [
            CheckResult(
                name="ffmpeg", passed=False, critical=True, message="Fail", recommendation="install"
            ),
        ],
    )
    passed = run_doctor(target_dir=tmp_path)
    assert not passed
    captured = capsys.readouterr().out
    assert "Se encontraron problemas" in captured


def test_main_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main CLI entrypoint help output."""
    sys.argv = ["playlist-sync"]
    main()
    out = capsys.readouterr().out
    assert "Playlist Sync v0.1.0" in out


def test_main_cli_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main CLI delegating to doctor."""
    monkeypatch.setattr("playlist_sync.main.run_doctor", lambda: True)
    sys.argv = ["playlist-sync", "doctor"]
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0


def test_doctor_defaults(tmp_path: Path) -> None:
    """Test default SystemDoctor helper methods."""
    doctor = SystemDoctor()
    code, out = doctor._default_run(["non_existent_command_12345"])
    assert code != 0

    assert isinstance(doctor._default_ytdlp_version(), (str, type(None)))

    total, used, free = doctor._default_disk_usage(tmp_path)
    assert total > 0

    write_ok = doctor._default_write_test(tmp_path)
    assert write_ok is True
