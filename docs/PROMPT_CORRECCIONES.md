# PROMPT DE CORRECCIONES — Playlist Sync (post-auditoría)

> **Uso:** copia este archivo a `docs/PROMPT_CORRECCIONES.md` en el repo. Junto con `PROMPT_MAESTRO.md` y `docs/AUDITORIA.md` es la fuente de verdad de esta etapa.

---

## 0. Reglas de trabajo (leer primero, siempre)

Eres el ingeniero que corrige los hallazgos de `docs/AUDITORIA.md`. El código anterior se construyó con un modelo básico y la auditoría encontró que **varias afirmaciones de sus reportes eran falsas** (por ejemplo, una función "implementada" que no existía). Por eso, en esta etapa **nada cuenta como hecho sin evidencia**.

1. **Lee** `PROMPT_MAESTRO.md`, `docs/AUDITORIA.md` y este archivo antes de tocar código.
2. **Una etapa a la vez (R0, R1…R6).** Al terminar cada una: reporte con evidencia, tag `fix-RN-completa` y **detente** hasta que el dueño escriba "aprobada". Nunca encadenes etapas. (El constructor anterior encadenó las fases 0 a 6 sin parar; no repitas eso.)
3. **Para cada hallazgo, en este orden:** (a) escribe una prueba que **falle** reproduciendo el problema, (b) muestra la salida del fallo, (c) corrige, (d) muestra que la prueba pasa, (e) corre la suite completa (`pytest -m "not network"`, `ruff check .`, `ruff format --check .`, `mypy src/playlist_sync`).
4. **Prohibido debilitar pruebas** para que pasen. Si una prueba existente es incorrecta, explica por qué y pide aprobación antes de cambiarla.
5. **Afirmaciones con prueba:** si dices "implementé X", incluye el comando que lo demuestra y su salida. Si no puedes demostrarlo, di "no verificado".
6. **No agregues alcance.** Solo se corrigen los hallazgos listados abajo. Ideas nuevas van a `docs/ideas-futuras.md`.
7. **Verifica contra documentación actual** (yt-dlp, FastAPI, Syncthing-Fork, etc.) antes de usar una opción; no confíes en la memoria ni en lo que dice la auditoría sobre versiones o mantenedores sin comprobarlo.
8. **Commits pequeños:** `fix-RN: H-xx descripción`. Registra decisiones nuevas en `docs/DECISIONS.md`.
9. **Portabilidad:** todo debe funcionar en Linux Mint 22.3 (producción) y Windows 11 (desarrollo).
10. **Reglas inviolables heredadas:** nunca se borra audio de `music_root` (RF-12); sin `shell=True`; mensajes al usuario en español claro.

### Formato del reporte de cada etapa
```
## Reporte Etapa RN
- Hallazgos tratados: [H-xx …]
- Por cada uno: prueba que falló (salida) → corrección → prueba que pasa (salida)
- Suite completa: resultado de pytest / ruff / mypy / cobertura de core
- Comandos para que el dueño lo verifique
- Cosas NO verificadas y por qué
- Decisiones nuevas
- Qué sigue y qué necesito del dueño
```

---

## Etapa R0 — Base y verdad (antes de corregir bugs)

**Objetivo:** alinear la documentación y comprobar que el núcleo funciona contra YouTube real. Hasta hoy **nunca se probó contra la red real**.

1. **Sincronizar `PROMPT_MAESTRO.md`:** el dueño reemplazará el archivo del repo por la versión actualizada (que incluye RF-19, RF-20, RNF-10 y la regla 13). Tras eso, relee y reporta qué requisitos **no existen aún en el código** (en especial **RF-20: reconciliar con el disco**, que no está implementado; la auditoría lo confundió con respaldos).
2. **H-08 (parte dependencias):** cambiar a `yt-dlp[default]` en `pyproject.toml`, `start.sh`, `start.bat` y el servicio, verificando en la documentación vigente de yt-dlp qué componente exige Deno. Reinstalar el entorno.
3. **H-14 (glob):** revisar si esa línea es la que **localiza el MP3 recién descargado**. Si lo es, la descarga real fallaría aunque las pruebas con mocks pasen. Corregir con `glob.escape` o comparando `name.endswith(...)`, con prueba usando un `external_id` real de 11 caracteres.
4. **Prueba en red real:** correr `pytest -m network -v` con la playlist pública de prueba del dueño (pídesela). Reportar el resultado completo, incluidos fallos. Si algo falla, **detente y repórtalo**: es prioridad sobre el resto.

**Criterio de cierre:** pruebas de red pasan; una playlist real se descarga con `[external_id]` en el nombre, portada y etiquetas; la segunda corrida no repite nada.

---

## Etapa R1 — Pérdida de datos y seguridad de la regla RF-12

- **H-05:** el umbral del 50 % trunca enteros. Usar comparación flotante o `math.ceil`. Pruebas: 3→1, 5→2, 7→3 deben abortar; 4→2 exacto no.
- **H-02:** respaldos SQLite. Quitar el truncado a 0 bytes. Los respaldos viven en la carpeta de datos (no en `music_root`) y la limpieza solo puede borrar archivos de respaldo **dentro de esa carpeta**, con una guarda que lo compruebe. Mantener intacta la prueba AST que impide borrar audio en `music_root`; si hace falta, acotarla explícitamente a `music_root`/audio y justificarlo en DECISIONS. Implementar `restore_database_backup(backup_file, db_path)`, un comando CLI (`restore-backup`) y pruebas: 12 rotaciones con `max_backups=5` dejan 5 válidos y no vacíos; restaurar recupera los datos.
- **H-13:** si un ítem `removed_remote=1` reaparece en la playlist, debe volver a `removed_remote=0` y al `.m3u8`. Además, un ítem `DOWNLOADED` cuyo archivo ya no existe en disco debe volver a `pending`. Pruebas para ambos casos.
- **H-01:** ordenar el `.m3u8` de podcasts con clave homogénea `(published_at or datetime.min, id)`, normalizando zonas horarias. Prueba con fechas mixtas `datetime`/`None`.

---

## Etapa R2 — Podcasts

- **H-06:** si el enclosure no es MP3 (por `Content-Type`, extensión o cabecera mágica), convertir con ffmpeg (lista de argumentos, `shell=False`) antes de etiquetar. Pruebas con fixtures `.m4a` y `.ogg` reales pequeños.
- **H-07:** verificar `downloaded_bytes == Content-Length` antes de mover el `.part`; limpiar `.part` fallidos sin tocar archivos completos; reanudación con `Range` solo si el servidor lo soporta. Pruebas con servidor simulado que corta la conexión.
- **H-15:** agregar `artist` a `RemoteItem`/`ItemRecord` desde `uploader`/`channel`/`itunes:author`; detectar WebP y convertir portada a JPEG (o etiquetar el MIME correcto). Pruebas de lectura de etiquetas con mutagen.

---

## Etapa R3 — Seguridad

- **H-03:** una única función de validación de URLs externas: solo `http/https`, resolución DNS y rechazo de IPs privadas, loopback, link-local, multicast y reservadas, **también en cada redirección** (hook de `httpx`); límite de tamaño para XML y portadas; aplicarla a `_fetch_xml`, `RssSource.download` (incluido el esquema del `enclosure`) y `download_cover_image`. Reemplazar `ET.fromstring` por `defusedxml` o `feedparser`. Pruebas con `127.0.0.1`, `192.168.x.x`, `169.254.169.254`, redirección a IP interna y XML con entidades anidadas.
- **H-10:** eliminar `CORSMiddleware` (la UI se sirve del mismo origen) o restringirlo al origen configurado. Prueba: un `Origin` externo no recibe cabeceras CORS permisivas.
- **Extra de la auditoría:** no exponer `technical_detail` en respuestas JSON de error; dejarlo solo en logs.

---

## Etapa R4 — Operación en Linux Mint

- **H-08 (resto):** servicio systemd con `Environment="PATH=%h/.deno/bin:/usr/local/bin:/usr/bin:/bin"` y ruta del repo sustituida dinámicamente por `install-service.sh`.
- **H-17:** configurar `sleep_interval` y `sleep_interval_requests` (y límite de velocidad) desde `config.toml`; mover la auto-actualización de yt-dlp a Python, registrando resultado en el log, con prueba con y sin red (simulada).
- **RF-20 (reconciliar con disco):** implementar según `PROMPT_MAESTRO.md`: escanear `music_root` y marcar como `downloaded` los ítems cuyo archivo existe por `[external_id]`. Botón y comando; pruebas.
- **H-04:** `install.ps1`: separar ejecutable y argumentos (`py` + `-3.12`). Menor prioridad (Windows es solo desarrollo), pero se corrige aquí.

---

## Etapa R5 — Concurrencia y experiencia de usuario

- **H-11:** adquirir el candado **antes** de crear la tarea (TOCTOU). Prueba con dos peticiones simultáneas: una 200 y la otra 409.
- **H-12:** `retry_item` debe comprobar el candado antes de mutar la base de datos, reiniciar `attempts` a 0, respetar `retryable=False` (`AGE_RESTRICTED`, `GEO_BLOCKED`) y aplicar espera creciente en errores transitorios (`RATE_LIMITED`, `NETWORK`). Pruebas, incluida la llamada exitosa 200 a `/retry`.
- **H-09:** al agregar una fuente, poblar los elementos iniciales como `pending` (con conteo); en la UI, si `source.status === 'error'`, mostrar "Hubo un problema" y `last_error_message`, nunca "Al día ✓".
- **H-16:** el progreso debe enviar `item_index` y `total_to_download` y la UI mostrar "Descargando 2 de 5"; `_run_sync_all_task` debe capturar `AppError` y emitir `err.code` y `err.user_message`, no `str(exc)`.

---

## Etapa R6 — Higiene y cierre de la Fase 7

- **H-18:** fijar versiones probadas (o lockfile) y usar `feedparser` o quitarlo de dependencias.
- **H-19:** completar `docs/manual-checks.md` (flujo E2E de Fase 7 con casillas), agregar una prueba E2E en `tests/e2e/` con `FakeSource` (añadir → sincronizar → archivos y `.m3u8` correctos → segunda corrida sin cambios), verificar en fuentes actuales cuál es el Syncthing-Fork mantenido y corregir `docs/syncthing.md`, y documentar en el README cómo exponer el servidor en la LAN (`host = "0.0.0.0"`) con la advertencia de red sin autenticación.
- **H-20:** cargar `config.toml` antes de `doctor`; prefijar nombres reservados de Windows (`CON`, `NUL`, `AUX`, `COM1`…); eliminar el CSS duplicado; hacer navegable por teclado el indicador de salud; documentar en DECISIONS los archivos fuera de la estructura 5.3 (`composite_source.py`, `adapters/web.py`, `logging_config.py`) y revisar el comportamiento implícito de `CompositeSource.inspect()` con búsqueda automática en iTunes.
- Completar la Tabla 1.4 de `PROMPT_MAESTRO.md` con los datos reales y crear el tag `fase-7-completa` solo si se cumplen sus criterios de aceptación.

---

## Cierre

Al terminar R6: ejecuta el checklist de manual-checks en la PC con Linux Mint (instalación con `install.sh`, servicio systemd, reinicio sin sesión, acceso desde el celular en la LAN, sincronización con Syncthing) y entrega el reporte final. El dueño volverá a correr una **re-auditoría con otro modelo** antes de dar el proyecto por terminado.

