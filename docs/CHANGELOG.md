# Changelog

Todas las modificaciones notables del proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [Unreleased]
### Fase 1 - Núcleo de descarga (sin web)
- Modelos de dominio (`core/models.py`) y reglas de sincronización incremental (`core/sync_rules.py`).
- Catálogo y mapeo exhaustivo de errores de yt-dlp a mensajes en español (`core/errors.py`).
- Repositorio SQLite con migraciones y detección insensible a mayúsculas/minúsculas (`adapters/repo.py`).
- Adaptador yt-dlp (`adapters/ytdlp_source.py`) con extracción plana, progreso y conversión MP3 vía ffmpeg.
- Servicio de orquestación de sincronización (`services/sync.py`) con control de espacio en disco y umbral de seguridad RF-12.
- CLI completa (`python -m playlist_sync` con comandos `add`, `sync`, `status` y `doctor`).
- Pruebas unitarias completas e integración con `FakeSource` y pruebas live con `@pytest.mark.network`.

### Fase 0 - Cimientos y confirmación de datos
- Estructura base del proyecto y configuración multi-plataforma (Linux Mint 22.3 y Windows 11).
- Herramienta de diagnóstico de salud del sistema `doctor.py` (RF-15) con salida en español.
- Configuración de dependencias en `pyproject.toml` fijando versiones y linters (`ruff`, `pytest`, `pytest-cov`, `mypy`).
- Scripts de instalación con entornos virtuales (`install.sh`, `install.ps1`).
- Archivos `.gitattributes` y `.gitignore`.
- Registro inicial de decisiones en `docs/DECISIONS.md`.

