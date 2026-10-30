# Registro de Decisiones de Arquitectura (ADR)

Este documento registra las decisiones técnicas tomadas a lo largo del proyecto, indicando fecha, contexto, decisión adoptada, motivos y alternativas descartadas.

---

## ADR-001: Stack tecnológico base
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Lenguaje: Python 3.12.
  - Servidor web: FastAPI + Uvicorn.
  - Base de datos: SQLite nativo (`sqlite3`), sin ORM pesado, con capa de repositorio propia y migraciones por versión.
  - Descargas YouTube: `yt-dlp` como módulo de Python con *progress hooks*.
  - Conversión de audio: `ffmpeg` externo.
  - Runtime JS: Deno (o Node) para la extracción de firmas de YouTube en yt-dlp.
  - Metadatos y portadas: `mutagen` para manipulación de etiquetas ID3.
  - Podcasts RSS: `httpx` + `feedparser`.
  - Frontend: HTML5 + CSS + JavaScript vanilla (sin paso de compilación / buildless), PWA.
  - Comunicación en vivo: Server-Sent Events (SSE).
  - Pruebas y calidad: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff` (linter/formateador) y `mypy` en `core/`.
- **Motivo:** Mantener el software 100% de código abierto, gratuito, ligero para PCs con recursos limitados, y sin requerir cadenas de construcción complejas en frontend ni backend.
- **Alternativas descartadas:** Django (muy pesado), SQLAlchemy (excesivo para el modelo requerido), frameworks de JS como React/Vue (innecesarios para una app local con UI de pantalla única).

---

## ADR-002: Descarte de Pinchflat y construcción de app propia
- **Fecha:** 2026-10-30
- **Decisión:** Omitir la evaluación de Pinchflat y proceder con el desarrollo a medida de Playlist Sync.
- **Motivo:** El dueño del proyecto decidió explícitamente construir una solución ligera, adaptada exactamente a sus necesidades (portadas embebidas, sincronización incremental estricta, archivos .m3u8 relativos para reproductores móviles, compatibilidad con Syncthing y UI "a prueba de mamá" sin Docker obligatorio).
- **Alternativas descartadas:** Adopción de Pinchflat.

---

## ADR-003: Compatibilidad multiplataforma (Linux Mint 22.3 y Windows 11)
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Producción: Linux Mint 22.3 (base Ubuntu 24.04 LTS "noble"), Python 3.12.3.
  - Desarrollo: Windows 11.
  - Portabilidad: Soporte simultáneo en ambos sistemas. Todo script, comando y prueba debe funcionar en Linux y Windows.
  - Scripts de instalación: `install.sh` y `install.ps1`, ambos forzando el uso de entornos virtuales (`venv`) debido a las restricciones de PEP 668 en Ubuntu 24.04.
  - Formato de fin de línea: `.gitattributes` fija `eol=lf` para scripts `*.sh`.
  - Detección de colisiones de archivos: Comparación insensible a mayúsculas y minúsculas (case-insensitive) para evitar discrepancias entre sistemas de archivos NTFS/FAT32 y ext4.
- **Motivo:** Garantizar despliegue y desarrollo sin fricción entre entornos y respetar las políticas de paquetes del sistema operativo.
- **Alternativas descartadas:** Forzar Docker para desarrollo/producción (descartado por requisito de bajo consumo y simplicidad en PC vieja).

---

## ADR-004: Modelo de ejecución y concurrencia de biblioteca
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Solo debe haber un servidor activo a la vez sobre la misma carpeta de música.
  - Cada máquina mantiene su propia base de datos SQLite local.
  - La migración entre equipos o respaldo de fuentes se realizará exportando/importando `sources.json`.
  - En Linux, el arranque automático para operación desatendida se implementará mediante un servicio de usuario en `systemd` con `loginctl enable-linger` (Fase 6).
- **Motivo:** Evitar bloqueos de base de datos o condiciones de carrera sobre los archivos de audio en la carpeta compartida o sincronizada.
- **Alternativas descartadas:** Base de datos compartida en red o SQLite alojado en carpetas sincronizadas por Syncthing.

---

## ADR-005: Clasificación y normalización de errores
- **Fecha:** 2026-10-30
- **Decisión:** Aislamiento de todo el análisis de mensajes de error de `yt-dlp` en `core/errors.py`. Se mapean a excepciones `AppError` con códigos estándar y mensajes en español claro orientados al usuario final según la sección 6.3 de PROMPT_MAESTRO.md.
- **Motivo:** Cumplir el principio UX "a prueba de mamá" y evitar que cambios o excepciones crudas de YouTube o yt-dlp ensucien la lógica de negocio o la interfaz.
- **Alternativas descartadas:** Mostrar errores técnicos de yt-dlp en la CLI o UI.

---

## ADR-006: Sincronización incremental y umbral de seguridad (RF-12)
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Si una playlist remota devuelve 0 elementos o menos del 50% de `last_known_count`, la sincronización se aborta de inmediato con código `EMPTY_OR_SHRUNK`.
  - Los elementos que desaparecen remotamente se marcan como `removed_remote = 1` en SQLite sin eliminar ningún archivo del disco.
  - Sincronización idempotente: los elementos con estado `DOWNLOADED` se omiten automáticamente en corridas posteriores.
- **Motivo:** Protección estricta contra pérdida de archivos o fallos temporales en las APIs de YouTube.
- **Alternativas descartadas:** Borrado sincronizado de canciones locales.

---

## ADR-007: Formato de metadatos ID3v2.3 y listas de reproducción .m3u8
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Uso de ID3v2.3 mediante `mutagen` para el etiquetado de canciones (título, artista, álbum, número de pista `n/total`, año, género y portada embebida tipo Front Cover).
  - Listas de reproducción `.m3u8` generadas con codificación UTF-8 sin BOM y rutas estrictamente relativas (solo nombre del archivo en la misma carpeta).
  - Al reordenar canciones, se actualiza únicamente la etiqueta `TRCK` y el archivo `.m3u8`, manteniendo invariables los nombres de los archivos en disco para no disparar re-transferencias innecesarias en Syncthing.
  - Ninguna parte del sistema elimina archivos de audio descargados (comprobado mediante pruebas de arquitectura).
- **Motivo:** Máxima compatibilidad con reproductores de Android/iOS/PC y eficiencia en la sincronización continua mediante Syncthing.
- **Alternativas descartadas:** Rutas absolutas en archivos m3u8 o renombrar archivos según su posición en la playlist.

---

## ADR-008: Servidor FastAPI, Server-Sent Events (SSE) y Candado de Concurrencia (RF-10, RF-11)
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Exposición de la API REST mediante FastAPI con endpoints delgados organizados en routers (`sources`, `sync`, `sse`, `health`).
  - La lógica de negocio pesada (descargas y sincronizaciones) se delega a `JobExecutor` ejecutando tareas en segundo plano vía `asyncio.to_thread`.
  - Candado de exclusión mutua global mediante `asyncio.Lock` (RF-11): solo se permite una sincronización activa a la vez. Intentos concurrentes devuelven `409 Conflict` con mensaje explicativo en español.
  - Streaming de progreso en tiempo real mediante Server-Sent Events (SSE) en `/events` (RF-10) con patrón pub/sub en memoria (`SSEBroadcaster`).
  - Rotación automática de logs con `RotatingFileHandler` (máximo 5 MB por archivo, 3 respaldos) (RNF-6).
- **Motivo:** Garantizar estabilidad de procesos de descarga, trazabilidad en vivo para la interfaz web y prevenir saturación de red, CPU y disco.
- **Alternativas descartadas:** WebSockets bidireccionales complejos o polling recurrente en la API.

---

## ADR-009: Frontend Vanilla "A prueba de mamá", SSE y Contingencia por Polling (RNF-5, RF-10)
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Frontend construido en Vanilla HTML5, CSS3 y JavaScript moderno sin frameworks (React, Vue), sin Node.js y sin paso de compilación (RNF-5).
  - Servido directamente como archivos estáticos en `/` por FastAPI mediante `adapters/web.py`.
  - Conexión reactiva en tiempo real mediante `EventSource('/events')` (RF-10) con reconexión automática y mecanismo de contingencia por polling cada 5 segundos si el stream SSE se interrumpe.
  - Diseño adaptable centrado en pantallas móviles (mínimo 360 px), soporte PWA (`manifest.webmanifest`), modo oscuro automático (`prefers-color-scheme`) y ausencia total de jerga técnica.
- **Motivo:** Máxima simplicidad de mantenimiento, longevidad del código, ejecución ligera en equipos de bajos recursos y usabilidad intuitiva para cualquier usuario.
- **Alternativas descartadas:** Single Page Apps con frameworks pesados (React, Vite, Tailwind con Node.js build step).

---

## ADR-010: Soporte Integral de Podcasts (RSS directo, YouTube Podcasts y Búsqueda iTunes) (RF-13, RF-14)
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Descarga directa de episodios de podcasts RSS mediante `adapters/rss_source.py` sin utilizar yt-dlp, leyendo streams de audio enclosures con barra de progreso y escritura segura.
  - Búsqueda pública de podcasts por nombre o tema mediante la API de iTunes Search (`adapters/itunes_search.py`), sin requerir claves de API.
  - Soporte de podcasts en YouTube (`kind=yt_podcast`) clasificando listas identificadas con `/podcast/` o títulos de podcast.
  - Generación de playlists `.m3u8` para podcasts ordenadas cronológicamente de más nuevo a más viejo (más reciente primero), y asignación automática del género ID3 "Podcast".
  - Adaptador unificado `CompositeSource` que enruta transparentemente peticiones entre YouTube, RSS directo y búsqueda de podcasts.
- **Motivo:** Brindar soporte completo a programas de audio sin sobrecargar el motor yt-dlp para feeds estándar y garantizar compatibilidad con reproductores móviles.
- **Alternativas descartadas:** Depender de yt-dlp para parsear feeds RSS de podcasts.

---

## ADR-011: Operación Continua, Respaldo Atómico y Migración Portátil (RNF-7, RF-16, RF-17)
- **Fecha:** 2026-10-30
- **Decisión:** 
  - Para producción en Linux Mint 22.3, el arranque desatendido se configura como un servicio de systemd de usuario (`systemd/playlist-sync.service`) con `loginctl enable-linger` para mantenerse activo sin inicio de sesión gráfico.
  - Actualización automática opcional del motor `yt-dlp` al arrancar (`start.sh` y `start.bat`), continuando con la versión instalada si no hay red (RF-16).
  - Programador de sincronización en segundo plano (`services/scheduler.py`, RF-17) con ciclo configurable (`interval_hours` en `config.toml`, por defecto cada 6 horas).
  - Respaldos atómicos automáticos de SQLite mediante la API `conn.backup` (`services/backup.py`) antes de iniciar el servidor.
  - Migración portátil e independiente entre máquinas mediante `sources.json` (`services/migration.py` y subcomandos CLI `export`/`import`), garantizando la regla de una sola instancia de servidor por carpeta de música.
- **Motivo:** Asegurar operación autónoma en la PC de destino, portabilidad total entre Linux y Windows, y protección contra pérdidas de datos.
- **Alternativas descartadas:** Servicios de Windows complejos con permisos de Administrador o compartir la base de datos binaria de SQLite entre computadoras.







