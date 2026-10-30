# Changelog

Todas las modificaciones notables del proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [Unreleased]
### Fase 3 - API y trabajos en segundo plano
- Servidor HTTP con FastAPI y middleware CORS (`api/app.py`).
- Endpoints REST para gestión de fuentes (`/sources`, `/sources/{id}`, `/sources/{id}/sync`), sincronización global (`/sync-all`), reintento de descargas fallidas (`/items/{id}/retry`) y diagnóstico de salud del sistema (`/health`).
- Streaming en vivo de progreso de sincronización mediante Server-Sent Events en `/events` (`api/routers/sse.py`, `services/jobs.py`, RF-10).
- Candado de exclusión mutua global mediante `asyncio.Lock` en `JobExecutor` para evitar descargas concurrentes retornando HTTP 409 Conflict (RF-11).
- Rotación automática de logs (`logging_config.py`) con `RotatingFileHandler` a 5 MB y 3 respaldos (RNF-6).
- Subcomando CLI `playlist-sync serve` para iniciar el servidor de desarrollo o producción con `uvicorn`.
- Suite de pruebas de integración de API y SSE utilizando `FastAPI TestClient` y `FakeSource`.

### Fase 2 - Biblioteca (archivos, etiquetas y playlists)
- Módulo de biblioteca local (`adapters/library.py`) y contrato `Library` (sección 5.2).
- Etiquetado ID3v2.3 completo con `mutagen` (`TIT2`, `TPE1`, `TALB`, `TRCK`, `TCON`, `TDRC`, `APIC`).
- Extracción inteligente de artista y título desde cadenas con separadores comunes.
- Descarga y persistencia de carátula de álbum `cover.jpg` y carátula embebida en MP3.
- Generador de listas `.m3u8` relativas con codificación UTF-8 sin BOM (RF-7, RNF-6).
- Idempotencia en la regeneración de playlists y actualización de posición sin renombrar archivos en disco.
- Prueba arquitectónica que valida la imposibilidad de borrado de archivos de audio (RF-12).

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

