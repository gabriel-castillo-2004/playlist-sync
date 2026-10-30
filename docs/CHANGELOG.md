# Changelog

Todas las modificaciones notables del proyecto se documentarán en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/).

## [Unreleased]
### Fase 6 - Operación diaria y migración (RNF-7, RF-16, RF-17)
- Script y servicio de usuario systemd para Linux Mint (`systemd/playlist-sync.service` y `systemd/install-service.sh`) con persistencia `loginctl enable-linger`.
- Verificación y auto-actualización opcional del motor `yt-dlp` al arrancar el servidor (`start.sh` y `start.bat`) (RF-16).
- Programador de sincronización en segundo plano (`services/scheduler.py`, RF-17) con ciclo configurable (`interval_hours`).
- Respaldo atómico de base de datos SQLite antes de arrancar (`services/backup.py`).
- Exportación e importación portátil de fuentes entre máquinas mediante `sources.json` (`services/migration.py`, `scripts/migrate_sources.py` y subcomandos CLI `export`/`import`).
- Documentación de cierre en `README.md` y guía completa de sincronización con Syncthing en `docs/syncthing.md`.
- Pruebas unitarias y de integración para scheduler, backup y migración JSON.

### Fase 5 - Podcasts (RSS, YouTube Podcasts y Búsqueda iTunes)
- Adaptador de podcasts RSS (`adapters/rss_source.py`) con parsing directo de XML sin yt-dlp y descarga streaming de enclosures de audio con progreso en vivo (RF-13).
- Adaptador de búsqueda de podcasts (`adapters/itunes_search.py`) consumiendo la API pública de Apple iTunes sin API key.
- Adaptador unificado `CompositeSource` (`adapters/composite_source.py`) para enrutar transparentemente URLs de YouTube, feeds RSS y búsquedas por nombre.
- Detección de Podcasts en YouTube (`SourceKind.YT_PODCAST`, RF-14).
- Orden cronológico más nuevo primero en archivos `.m3u8` y asignación de género "Podcast" en metadatos ID3.
- Endpoint de búsqueda de podcasts `GET /podcasts/search` (`api/routers/podcasts.py`).
- Interfaz web actualizada para buscar podcasts por nombre o link directo con selección interactiva.
- Fixtures de prueba XML (`valid_podcast.xml`, `no_cover_podcast.xml`, `weird_enclosure_podcast.xml`) y pruebas unitarias/integración (`test_itunes_search.py`, `test_rss_source.py`, `test_podcasts.py`).

### Fase 4 - Interfaz web "a prueba de mamá"
- Adaptador web (`adapters/web.py`) para servir la aplicación estática en `/` y endpoints de carátulas (`/covers/{id}`).
- Pantalla única responsive (`web/index.html`) utilizable con una sola mano en pantallas móviles (desde 360 px).
- Estilos CSS puros (`web/styles.css`, `web/style.css`) con variables personalizadas, botones táctiles y soporte automático para modo oscuro (`prefers-color-scheme`).
- Lógica en Vanilla JavaScript (`web/app.js`, RNF-5) sin dependencias ni paso de compilación.
- Conexión reactiva en tiempo real vía Server-Sent Events (`EventSource('/events')`, RF-10) con reconexión y polling de contingencia cada 5s si el stream se interrumpe.
- Tarjetas de fuentes con estados en español claro ("Al día ✓", "X nuevas — Descargar", "Descargando...", "Hubo un problema").
- Soporte PWA con manifiesto web (`web/manifest.webmanifest`) e iconos vectoriales y PNG (`web/icons/`).
- Documento de comprobaciones manuales en `docs/manual-checks.md`.
- Pruebas automatizadas de integración web (`tests/integration/test_web.py`).

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

