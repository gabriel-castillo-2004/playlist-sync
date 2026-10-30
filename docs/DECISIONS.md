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


