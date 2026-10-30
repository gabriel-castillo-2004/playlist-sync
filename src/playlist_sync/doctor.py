"""System health diagnostics for Playlist Sync (RF-15)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    """Result of an individual diagnostic check."""

    name: str
    passed: bool
    critical: bool
    message: str
    recommendation: str | None = None


class SystemDoctor:
    """Performs diagnostic checks on system prerequisites."""

    def __init__(
        self,
        python_version: tuple[int, int, int] | None = None,
        which_fn: Callable[[str], str | None] | None = None,
        run_fn: Callable[[list[str]], tuple[int, str]] | None = None,
        ytdlp_version_fn: Callable[[], str | None] | None = None,
        disk_usage_fn: Callable[[Path], tuple[int, int, int]] | None = None,
        write_test_fn: Callable[[Path], bool] | None = None,
    ) -> None:
        self.python_version = python_version or sys.version_info[:3]
        self.which_fn = which_fn or shutil.which
        self.run_fn = run_fn or self._default_run
        self.ytdlp_version_fn = ytdlp_version_fn or self._default_ytdlp_version
        self.disk_usage_fn = disk_usage_fn or self._default_disk_usage
        self.write_test_fn = write_test_fn or self._default_write_test

    @staticmethod
    def _default_run(cmd: list[str]) -> tuple[int, str]:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )
            return res.returncode, (res.stdout + res.stderr).strip()
        except Exception as exc:
            return 1, str(exc)

    @staticmethod
    def _default_ytdlp_version() -> str | None:
        try:
            import yt_dlp  # type: ignore[import-untyped]

            version = getattr(yt_dlp.version, "__version__", None)
            return str(version) if version else "desconocida"
        except ImportError:
            return None

    @staticmethod
    def _default_disk_usage(path: Path) -> tuple[int, int, int]:
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(target)
        return usage.total, usage.used, usage.free

    @staticmethod
    def _default_write_test(path: Path) -> bool:
        test_file = path / ".write_test_tmp"
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def check_python(self) -> CheckResult:
        """Check that Python version is >= 3.12."""
        major, minor, patch = self.python_version
        ver_str = f"{major}.{minor}.{patch}"
        if (major, minor) >= (3, 12):
            return CheckResult(
                name="Python",
                passed=True,
                critical=True,
                message=f"Instalado (versión {ver_str})",
            )
        return CheckResult(
            name="Python",
            passed=False,
            critical=True,
            message=f"Versión no compatible ({ver_str}). Se requiere Python 3.12 o superior.",
            recommendation="Actualiza Python a la versión 3.12 o posterior (ej. en Ubuntu: apt install python3.12).",
        )

    def check_ffmpeg(self) -> CheckResult:
        """Check that ffmpeg is installed and executable."""
        path = self.which_fn("ffmpeg")
        if not path and sys.platform == "win32" and self.which_fn is shutil.which:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                candidates = list(
                    Path(local_app_data).glob(
                        "Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg*/bin/ffmpeg.exe"
                    )
                )
                if candidates:
                    path = str(candidates[0])

        if not path:
            return CheckResult(
                name="ffmpeg",
                passed=False,
                critical=True,
                message="No se encontró ffmpeg en el sistema.",
                recommendation=(
                    "En Linux: ejecuta 'sudo apt install ffmpeg'. "
                    "En Windows: ejecuta 'winget install Gyan.FFmpeg' y reinicia la terminal."
                ),
            )
        code, out = self.run_fn([path, "-version"])
        if code == 0:
            first_line = out.splitlines()[0] if out else "ffmpeg presente"
            return CheckResult(
                name="ffmpeg",
                passed=True,
                critical=True,
                message=f"Instalado ({first_line})",
            )
        return CheckResult(
            name="ffmpeg",
            passed=False,
            critical=True,
            message="ffmpeg está en PATH pero devolvió un error al ejecutarse.",
            recommendation="Comprueba la instalación de ffmpeg y sus dependencias.",
        )

    def check_js_runtime(self) -> CheckResult:
        """Check for Deno (preferred) or Node.js runtime for yt-dlp."""
        deno_path = self.which_fn("deno")
        if not deno_path and sys.platform == "win32" and self.which_fn is shutil.which:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                candidates = list(
                    Path(local_app_data).glob("Microsoft/WinGet/Packages/DenoLand.Deno*/deno.exe")
                )
                if candidates:
                    deno_path = str(candidates[0])

        if deno_path:
            code, out = self.run_fn([deno_path, "--version"])
            first_line = out.splitlines()[0] if out and code == 0 else "Deno presente"
            return CheckResult(
                name="Runtime JS (Deno/Node)",
                passed=True,
                critical=False,
                message=f"Instalado (Deno: {first_line})",
            )

        node_path = self.which_fn("node")
        if node_path:
            code, out = self.run_fn(["node", "--version"])
            first_line = out.splitlines()[0] if out and code == 0 else "Node.js presente"
            return CheckResult(
                name="Runtime JS (Deno/Node)",
                passed=True,
                critical=False,
                message=f"Instalado (Node.js: {first_line})",
            )

        return CheckResult(
            name="Runtime JS (Deno/Node)",
            passed=False,
            critical=False,
            message="No se encontró Deno ni Node.js.",
            recommendation=(
                "Recomendado para resolver retos de YouTube en yt-dlp. "
                "En Linux instala Deno con: 'curl -fsSL https://deno.land/install.sh | sh'. "
                "En Windows con: 'winget install DenoLand.Deno'."
            ),
        )

    def check_ytdlp(self) -> CheckResult:
        """Check that yt-dlp is available in the environment."""
        version = self.ytdlp_version_fn()
        if version:
            return CheckResult(
                name="yt-dlp",
                passed=True,
                critical=True,
                message=f"Instalado (versión {version})",
            )
        return CheckResult(
            name="yt-dlp",
            passed=False,
            critical=True,
            message="El módulo 'yt-dlp' no está instalado en el entorno de Python.",
            recommendation="Instálalo en tu entorno virtual con: 'pip install yt-dlp'.",
        )

    def check_disk_space(self, target_dir: Path, min_mb: int = 1024) -> CheckResult:
        """Check available disk space in the destination folder."""
        try:
            total, used, free = self.disk_usage_fn(target_dir)
            free_mb = free // (1024 * 1024)
            free_gb = free_mb / 1024.0
            if free_mb >= min_mb:
                return CheckResult(
                    name="Espacio en disco",
                    passed=True,
                    critical=True,
                    message=f"Suficiente: {free_gb:.1f} GB disponibles (mínimo requerido: {min_mb} MB)",
                )
            return CheckResult(
                name="Espacio en disco",
                passed=False,
                critical=True,
                message=f"Espacio insuficiente: solo hay {free_mb} MB libres (se requieren al menos {min_mb} MB).",
                recommendation="Libera espacio en el disco antes de iniciar descargas.",
            )
        except Exception as exc:
            return CheckResult(
                name="Espacio en disco",
                passed=False,
                critical=True,
                message=f"No se pudo consultar el espacio en disco: {exc}",
                recommendation="Verifica que la ruta de almacenamiento exista o sea accesible.",
            )

    def check_write_permissions(self, target_dir: Path) -> CheckResult:
        """Check write permissions in the target directory."""
        if self.write_test_fn(target_dir):
            return CheckResult(
                name="Permisos de escritura",
                passed=True,
                critical=True,
                message=f"Correctos en '{target_dir}'",
            )
        return CheckResult(
            name="Permisos de escritura",
            passed=False,
            critical=True,
            message=f"No se tienen permisos de escritura en '{target_dir}'.",
            recommendation=(
                "En Linux: revisa el propietario de la carpeta con 'sudo chown -R $USER <ruta>'. "
                "En Windows: comprueba la seguridad de la carpeta en sus Propiedades."
            ),
        )

    def run_all(self, target_dir: Path | None = None, min_mb: int = 1024) -> list[CheckResult]:
        """Run all diagnostic checks."""
        dir_to_check = target_dir or Path("music_root").resolve()
        return [
            self.check_python(),
            self.check_ffmpeg(),
            self.check_js_runtime(),
            self.check_ytdlp(),
            self.check_disk_space(dir_to_check, min_mb=min_mb),
            self.check_write_permissions(dir_to_check),
        ]


def run_doctor(target_dir: Path | None = None, min_mb: int = 1024) -> bool:
    """CLI runner for doctor. Returns True if all critical checks pass."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    doctor = SystemDoctor()
    results = doctor.run_all(target_dir=target_dir, min_mb=min_mb)

    print("=" * 60)
    print("Playlist Sync — Diagnostico de Salud del Sistema")
    print("=" * 60)

    all_passed = True
    for res in results:
        status_tag = "OK" if res.passed else ("AVISO" if not res.critical else "ERROR")
        category = "OPCIONAL" if not res.critical else "REQUERIDO"
        print(f"[{status_tag}] {res.name} ({category})")
        print(f"    {res.message}")
        if not res.passed and res.recommendation:
            print(f"    -> Solucion: {res.recommendation}")
        if res.critical and not res.passed:
            all_passed = False
        print("-" * 60)

    if all_passed:
        print("\nEl sistema cumple con los requisitos necesarios para operar.")
    else:
        print("\nSe encontraron problemas que deben resolverse antes de continuar.")

    return all_passed


if __name__ == "__main__":
    success = run_doctor()
    sys.exit(0 if success else 1)
