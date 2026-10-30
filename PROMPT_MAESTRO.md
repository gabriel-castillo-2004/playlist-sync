\# PROMPT MAESTRO — "Playlist Sync": app web local para descargar playlists y podcasts como MP3



> \\\*\\\*Cómo usar este archivo:\\\*\\\* colócalo en la raíz del repositorio como `PROMPT\\\_MAESTRO.md` y dile a la IA de VS Code: \\\*"Lee `PROMPT\\\_MAESTRO.md` completo y sigue la sección 0. Empieza por la Fase 0."\\\* Este documento es la \\\*\\\*fuente de verdad\\\*\\\*. Si algo del chat contradice este archivo, gana este archivo, salvo que el dueño del proyecto lo modifique explícitamente.



\---



\## 0. Reglas de trabajo para la IA (LEER PRIMERO, SIEMPRE)



Eres el ingeniero principal de este proyecto. El dueño no es experto en este stack y necesita que construyas \*\*exactamente\*\* lo descrito, en fases, con pruebas, sin desviarte.



1\. \*\*Lee todo este archivo antes de escribir código.\*\* Al inicio de cada sesión, relee las secciones 1, 2, 3 y la fase actual.

2\. \*\*Una fase a la vez.\*\* Nunca avances a la siguiente fase sin que (a) todos los criterios de aceptación de la fase actual se cumplan, (b) todas las pruebas pasen y (c) el dueño apruebe explícitamente.

3\. \*\*Pruebas primero o junto al código.\*\* Ninguna fase termina sin pruebas automáticas. Si no puedes probar algo automáticamente, escribe una lista de verificación manual en `docs/manual-checks.md`.

4\. \*\*No inventes alcance.\*\* Si una idea no está en este archivo, \*\*no la implementes\*\*. Anótala en `docs/ideas-futuras.md` y sigue. Ver sección 3 (fuera de alcance).

5\. \*\*Ante ambigüedad, pregunta\*\* (máximo 3 preguntas concretas, con una opción recomendada cada una). No adivines requisitos.

6\. \*\*No confíes en tu memoria para APIs de librerías.\*\* yt-dlp, FastAPI, mutagen y demás cambian. Antes de usar una opción o función, verifica la documentación oficial vigente y \*\*fija versiones\*\* en `pyproject.toml`. Si una opción de este documento ya no existe, repórtalo en vez de improvisar.

7\. \*\*Commits pequeños\*\* con mensajes claros: `fase-N: descripción`. Un commit por unidad lógica; un tag `fase-N-completa` al cerrar cada fase.

8\. \*\*Registra decisiones\*\* en `docs/DECISIONS.md` (fecha, decisión, motivo, alternativas descartadas).

9\. \*\*Al cerrar cada fase entrega el "Reporte de fase"\*\* (sección 12) y \*\*detente\*\* esperando aprobación.

10\. \*\*Seguridad y robustez no son opcionales\*\* (sección 9). Nada de `shell=True`, nada de rutas sin sanear.

11\. \*\*Nunca borres archivos de música del usuario.\*\* Ninguna parte de este sistema elimina audio descargado (ver RF-12).

12\. \*\*Idioma:\*\* código, nombres de funciones y comentarios en inglés; \*\*toda la interfaz, mensajes de error al usuario y documentación para el usuario en español claro y sencillo.\*\*



\---



\## 1. Objetivo y contexto



\### 1.1 Qué es

Una aplicación web \*\*local\*\* que corre en una PC vieja con Windows (posible Linux). Desde cualquier dispositivo en la misma red (celular, laptop) se abre una página donde el usuario:



\- Guarda links de \*\*playlists públicas de YouTube / YouTube Music\*\* y \*\*podcasts\*\*.

\- Ve cuáles canciones/episodios ya están descargados, cuáles faltan y cuáles fallaron (con el motivo en español).

\- Pulsa \*\*"Actualizar"\*\* y la app descarga \*\*solo lo que falta\*\*, en MP3, con portada y metadatos.

\- Los archivos quedan organizados para que \*\*cualquier reproductor de música reconozca las playlists solo\*\*, sin crear playlists a mano.

\- Los archivos llegan al celular/laptop mediante Syncthing (se configura una vez, fuera del código; ver Fase 7).



\### 1.2 Problema que resuelve

Tener la música de las playlists de YouTube como archivos MP3 locales, ordenados y con portada, y mantenerlos al día agregando solo lo nuevo, con el mínimo de pasos posible.



\### 1.3 Principio rector de UX: "a prueba de mamá"

La persona que usa la página puede no ser técnica. Reglas:

\- Una sola pantalla principal. Sin menús profundos, sin jerga ("sync", "cookie", "archive" no aparecen en la UI).

\- Estados en palabras simples: \*\*"Al día ✓"\*\*, \*\*"3 nuevas — Descargar"\*\*, \*\*"Descargando 2 de 5…"\*\*, \*\*"Hubo un problema"\*\*.

\- Todo error explica \*\*qué pasó y qué hacer\*\*, en una frase.

\- Botones grandes, tocables con el dedo, legibles en pantalla de celular.

\- Cero configuración diaria. El único paso humano diario es (opcionalmente) pulsar "Actualizar todo".



\### 1.4 Datos por confirmar con el dueño (pregúntalos en la Fase 0)

| Dato | Valor |

|---|---|

| Sistema operativo y versión de la PC vieja | \*por confirmar\* |

| Versión de Python instalable en esa PC | \*por confirmar\* |

| ¿La PC estará siempre encendida o se prende bajo demanda? | \*por confirmar\* |

| 1–2 URLs de playlists públicas pequeñas (≤10 canciones) para pruebas | \*por confirmar\* |

| 1 podcast con RSS y 1 podcast en YouTube para pruebas | \*por confirmar\* |

| Reproductor de música que se usará en el celular | \*por confirmar\* |

| Carpeta de destino de la música | \*por confirmar\* |

| Espacio libre en disco | \*por confirmar\* |



\---



\## 2. Requisitos



\### 2.1 Funcionales (RF)

\- \*\*RF-1 Fuentes.\*\* Soportar dos tipos de fuente: `yt\\\_playlist` (playlist pública de YouTube o YouTube Music) y `podcast` (feed RSS, o canal/playlist de YouTube marcado como podcast).

\- \*\*RF-2 Alta de fuente.\*\* Pegar un link en la página registra la fuente. Se valida el link y se consulta la playlist \*\*sin descargar\*\* para obtener título, portada y lista de elementos.

\- \*\*RF-3 Detección de privadas.\*\* Si la playlist es privada o no accesible, se informa \*\*al agregarla\*\*, antes de descargar, con instrucciones en español (p. ej. "ponla como Pública o No listada en YouTube").

\- \*\*RF-4 Estado por elemento.\*\* Cada canción/episodio tiene estado: `pending`, `downloading`, `downloaded`, `error`. Los errores guardan un \*\*código\*\* y un \*\*mensaje\*\* legible.

\- \*\*RF-5 Incremental.\*\* "Actualizar" compara la lista remota con la base de datos y descarga \*\*solo lo que no está `downloaded`\*\*. Ejecutar dos veces seguidas no repite descargas.

\- \*\*RF-6 Formato.\*\* Audio en \*\*MP3\*\* con portada embebida y etiquetas ID3 (ver sección 6).

\- \*\*RF-7 Organización en disco.\*\* Una carpeta por fuente, un archivo `.m3u8` por fuente, nombres de archivo \*\*estables\*\* (ver sección 6).

\- \*\*RF-8 Reintentos.\*\* Un elemento con error puede reintentarse con un botón; hay un tope de reintentos automáticos (3) con espera creciente.

\- \*\*RF-9 Actualizar todo.\*\* Un botón global actualiza todas las fuentes, una a la vez.

\- \*\*RF-10 Progreso visible.\*\* La UI muestra avance en vivo ("Descargando 2 de 5") sin recargar la página.

\- \*\*RF-11 Un trabajo a la vez.\*\* Nunca corren dos sincronizaciones simultáneas (candado). Si ya hay una, la UI lo dice.

\- \*\*RF-12 Solo agregar, nunca borrar.\*\* El sistema \*\*nunca elimina\*\* archivos de audio. Si un elemento desaparece de la playlist remota, solo se marca como `removed\\\_remote` en la base de datos y \*\*se conserva el archivo\*\*. Si la lectura de una playlist devuelve 0 elementos o muchos menos que la última vez (< 50 % de lo conocido), la sincronización de esa fuente \*\*se aborta\*\* con mensaje claro y no cambia nada.

\- \*\*RF-13 Podcasts por RSS.\*\* Descargar episodios directamente del enlace del feed (sin yt-dlp), con la portada del programa. Búsqueda de podcasts \*\*por nombre\*\* usando la API pública de búsqueda de iTunes (sin llave; verificar documentación vigente). Orden: más nuevo primero en el `.m3u8`.

\- \*\*RF-14 Podcasts de YouTube.\*\* Se tratan como una fuente `yt\\\_playlist` con `kind=podcast` (mismas reglas, género ID3 "Podcast").

\- \*\*RF-15 Salud del sistema.\*\* Comando/endpoint `doctor` que verifica Python, ffmpeg, Deno (o Node), versión de yt-dlp, espacio en disco y permisos de escritura, e informa en español qué falta.

\- \*\*RF-16 Auto-actualización del motor.\*\* Al arrancar, la app intenta actualizar `yt-dlp` (si hay internet) y registra el resultado; si falla, continúa con la versión instalada.

\- \*\*RF-17 Sincronización programada (opcional, configurable).\*\* Mientras el servidor esté encendido, revisa automáticamente cada N horas (por defecto 6; 0 = desactivado).

\- \*\*RF-18 Instalable como app.\*\* La página incluye manifiesto PWA e ícono para guardarse en la pantalla de inicio.



\### 2.2 No funcionales (RNF)

\- \*\*RNF-1 Costo cero.\*\* Sólo software gratuito y de código abierto. Sin servicios de pago ni nube.

\- \*\*RNF-2 Local.\*\* Corre en la PC del usuario con su IP residencial. No se despliega a VPS ni a nubes gratuitas (YouTube bloquea IPs de centros de datos).

\- \*\*RNF-3 Mantenibilidad.\*\* Capas separadas; cada fuente es un módulo reemplazable detrás de una interfaz común (sección 5). Cambios de YouTube deben afectar a \*\*un solo módulo\*\*.

\- \*\*RNF-4 Pocos recursos.\*\* Debe funcionar en una PC vieja (poca RAM). Descargas secuenciales (concurrencia 1 por defecto).

\- \*\*RNF-5 Sin paso de compilación en el frontend.\*\* HTML + CSS + JS simples servidos por FastAPI. Sin Node/npm obligatorio.

\- \*\*RNF-6 Observabilidad.\*\* Logs rotativos en archivo, con nivel configurable.

\- \*\*RNF-7 Reproducibilidad.\*\* `README` con instalación paso a paso en Windows; un script `start.bat` que arranca todo.

\- \*\*RNF-8 Cobertura.\*\* ≥ 80 % de cobertura en el núcleo (`core/`), medida con `pytest-cov`.

\- \*\*RNF-9 Privacidad.\*\* Sin telemetría. No se almacenan credenciales. Las cookies (si algún día se usan) están fuera de alcance (ver 3).



\---



\## 3. Fuera de alcance (NO implementar)



No construyas nada de esto, aunque parezca buena idea. Anótalo en `docs/ideas-futuras.md` si surge:



\- Spotify y Tidal (ni lectura de playlists ni descargas).

\- Playlists \*\*privadas\*\* y manejo de cookies/credenciales de YouTube (solo detectar y avisar).

\- Borrado automático de música (RF-12).

\- Cuentas de usuario, login, multiusuario, permisos.

\- Despliegue en la nube / VPS / Docker como requisito.

\- Reproductor de música dentro de la app.

\- Apps móviles nativas.

\- Edición manual de etiquetas, ecualizador, letras.

\- Cualquier función de distribución o compartición pública del contenido descargado.

\- Sincronización con Syncthing \*\*dentro del código\*\* (se documenta y configura aparte, Fase 7).



> \\\*\\\*Aviso de uso:\\\*\\\* el proyecto es para \\\*\\\*uso personal\\\*\\\*. Descargar contenido puede infringir los términos de servicio de las plataformas; el README debe incluir esta advertencia y la app no debe facilitar su distribución.



\---



\## 4. Stack decidido (no cambiar sin aprobación)



| Área | Decisión | Nota |

|---|---|---|

| Lenguaje | Python (versión según Fase 0) | fijar en `pyproject.toml` |

| Servidor web | FastAPI + Uvicorn | |

| Base de datos | SQLite (módulo estándar `sqlite3`, capa de repositorio propia, migraciones simples por versión) | sin ORM pesado |

| Descargas YouTube | `yt-dlp` \*\*como módulo Python\*\* (API embebida), con \*progress hooks\* | actualizable con pip |

| Conversión | `ffmpeg` (externo, verificado por `doctor`) | |

| Runtime JS para yt-dlp | Deno (o Node) recomendado por yt-dlp para YouTube | verificar docs vigentes |

| Etiquetas / portada | `mutagen` | control total de ID3 |

| Podcasts RSS | `httpx` + `feedparser` | |

| Frontend | HTML + CSS + JS vanilla, mobile-first, PWA | sin build |

| Progreso en vivo | Server-Sent Events (o \*polling\* corto si SSE da problemas; decisión en `DECISIONS.md`) | |

| Pruebas | `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`/mocks para HTTP | |

| Calidad | `ruff` (lint + formato) y `mypy` básico en `core/` | |

| Configuración | `config.toml` (con valores por defecto y validación) | |



\---



\## 5. Arquitectura



\### 5.1 Capas

```

UI (HTML/JS)  →  API (FastAPI, routers delgados)  →  Services (casos de uso)

\&#x20;                                                       ↓

\&#x20;                             Core (dominio puro, sin red ni disco directo)

\&#x20;                                                       ↓

\&#x20;               Adapters: YtDlpSource · RssPodcastSource · Library(writer) · Repo(SQLite)

```

\- \*\*Core/dominio:\*\* modelos, reglas de sincronización (qué falta, umbral de seguridad, clasificación de errores). \*\*Sin\*\* llamadas de red ni de disco, para probarlo con facilidad.

\- \*\*Adapters:\*\* todo lo que toca el mundo exterior, detrás de interfaces (`Protocol`).

\- \*\*Services:\*\* orquestan casos de uso (`add\\\_source`, `sync\\\_source`, `sync\\\_all`, `retry\\\_item`).



\### 5.2 Interfaces clave (contratos; no cambiar firmas sin aprobación)

```python

class Source(Protocol):

\&#x20;   def inspect(self, url: str) -> SourceInfo: ...            # sin descargar: título, portada, tipo

\&#x20;   def list\\\_items(self, source: SourceRecord) -> list\\\[RemoteItem]: ...

\&#x20;   def download(self, item: RemoteItem, dest\\\_dir: Path,

\&#x20;                on\\\_progress: Callable\\\[\\\[Progress], None]) -> DownloadedFile: ...



class Library(Protocol):

\&#x20;   def finalize\\\_item(self, source: SourceRecord, item: ItemRecord, file: DownloadedFile) -> Path: ...

\&#x20;   def rebuild\\\_playlist\\\_file(self, source: SourceRecord, items: list\\\[ItemRecord]) -> Path: ...

```

Todos los errores se normalizan a `AppError(code, user\\\_message, technical\\\_detail, retryable)`.



\### 5.3 Estructura de carpetas

```

playlist-sync/

├─ PROMPT\\\_MAESTRO.md

├─ README.md

├─ pyproject.toml

├─ config.toml

├─ start.bat

├─ docs/  (DECISIONS.md, ideas-futuras.md, manual-checks.md, syncthing.md, CHANGELOG.md)

├─ src/playlist\\\_sync/

│  ├─ core/        (models.py, sync\\\_rules.py, errors.py)

│  ├─ adapters/    (ytdlp\\\_source.py, rss\\\_source.py, library.py, repo.py, itunes\\\_search.py)

│  ├─ services/    (sources.py, sync.py, scheduler.py, jobs.py)

│  ├─ api/         (routers, schemas, sse.py)

│  ├─ web/         (index.html, app.js, styles.css, manifest.webmanifest, icons/)

│  ├─ doctor.py

│  └─ main.py

└─ tests/  (unit/, integration/, fixtures/, e2e/)

```



\---



\## 6. Modelo de datos y formato de salida



\### 6.1 Tablas (mínimo)

\- `sources(id, kind, url, title, cover\\\_url, folder\\\_name, status, last\\\_sync\\\_at, last\\\_error\\\_code, last\\\_error\\\_message, last\\\_known\\\_count, created\\\_at)`

&#x20; - `kind`: `yt\\\_playlist` | `yt\\\_podcast` | `rss\\\_podcast`

\- `items(id, source\\\_id, external\\\_id, title, position, published\\\_at, status, error\\\_code, error\\\_message, attempts, file\\\_path, downloaded\\\_at, removed\\\_remote)`

&#x20; - `status`: `pending` | `downloading` | `downloaded` | `error`

&#x20; - Único: `(source\\\_id, external\\\_id)`

\- `settings(key, value)`

\- `schema\\\_version`



\### 6.2 Estructura en disco

```

<music\\\_root>/

└─ <Nombre de la fuente saneado>/

\&#x20;  ├─ <Título saneado> \\\[<external\\\_id>].mp3

\&#x20;  ├─ ...

\&#x20;  ├─ cover.jpg                    (portada de la fuente)

\&#x20;  └─ <Nombre de la fuente>.m3u8

```

\- \*\*Nombres estables:\*\* el nombre del archivo \*\*no incluye la posición\*\*. Motivo: si el usuario reordena su playlist, no se deben renombrar ni reenviar archivos por Syncthing. El orden vive en el `.m3u8` y en la etiqueta de pista.

\- \*\*`.m3u8`:\*\* codificación UTF-8, rutas \*\*relativas\*\* (solo nombre de archivo, ya que está en la misma carpeta), orden = orden de la playlist (podcasts: más nuevo primero). Se \*\*regenera por completo\*\* en cada sincronización (operación idempotente).

\- \*\*Etiquetas ID3 (mutagen):\*\* `title`, `artist` (autor del video/canal o del programa), `album` = nombre de la fuente, `track` = posición (`n/total`), portada embebida (JPEG), `genre` = "Podcast" para podcasts, `date` si existe.

\- \*\*Saneado de nombres:\*\* quitar caracteres inválidos en Windows (`<>:"/\\\\|?\\\*`), recortar espacios/puntos finales, limitar longitud total de ruta (< 240), manejar colisiones con el `external\\\_id`.



\### 6.3 Catálogo de errores (códigos → mensaje al usuario)

| Código | Mensaje (español claro) |

|---|---|

| `PRIVATE\\\_SOURCE` | "Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar." |

| `SOURCE\\\_NOT\\\_FOUND` | "No encontré esa playlist. Revisa que el link esté completo." |

| `INVALID\\\_URL` | "Ese link no parece de YouTube ni de un podcast." |

| `ITEM\\\_UNAVAILABLE` | "Este video ya no está disponible." |

| `AGE\\\_RESTRICTED` | "Este video tiene restricción de edad y no se puede descargar." |

| `GEO\\\_BLOCKED` | "Este video no está disponible en tu país." |

| `RATE\\\_LIMITED` | "YouTube pidió esperar un poco. Intenta de nuevo en unos minutos." |

| `NETWORK` | "No hay conexión a internet." |

| `DISK\\\_FULL` | "No hay espacio en el disco." |

| `TOOL\\\_MISSING` | "Falta un programa necesario ({nombre}). Ejecuta la revisión del sistema." |

| `EMPTY\\\_OR\\\_SHRUNK` | "La playlist apareció vacía o con muchas menos canciones. No cambié nada por seguridad." |

| `UNKNOWN` | "Ocurrió un problema inesperado. Se guardó el detalle técnico en el registro." |



El mapeo desde las excepciones/mensajes de yt-dlp debe estar \*\*aislado en un solo módulo\*\* y cubierto por pruebas con mensajes reales grabados como \*fixtures\*.



\---



\## 7. Plan por fases



> Cada fase incluye: \\\*\\\*Objetivo, Entregables, Criterios de aceptación, Pruebas y "No hacer"\\\*\\\*. Al terminar, genera el Reporte de fase (sección 12) y \\\*\\\*detente\\\*\\\*.



\### Fase 0 — Cimientos y confirmación de datos

\*\*Objetivo:\*\* proyecto listo, entorno verificado, datos del dueño confirmados.

\*\*Entregables:\*\*

\- Repositorio con estructura de 5.3 (carpetas vacías con `\\\_\\\_init\\\_\\\_`), `pyproject.toml` con versiones fijadas, `ruff`, `pytest`, `pytest-cov` configurados.

\- `config.toml` con valores por defecto.

\- `doctor.py` funcional (RF-15) con salida en español.

\- `README.md` inicial y `docs/DECISIONS.md` con las decisiones de la sección 4.

\- Tabla 1.4 completada (preguntas al dueño).

\*\*Criterios de aceptación:\*\* `python -m playlist\\\_sync.doctor` corre y reporta correctamente qué está instalado y qué falta; `pytest` corre (aunque haya pocas pruebas); `ruff` sin errores.

\*\*Pruebas:\*\* `doctor` con herramientas simuladas presentes y ausentes.

\*\*No hacer:\*\* no escribir lógica de descargas todavía.



> \\\*\\\*Paso humano opcional previo (1–2 h, el dueño):\\\*\\\* evaluar \\\*\\\*Pinchflat\\\*\\\* (gestor de YouTube autoalojado, gratuito) con esta lista: ¿genera MP3 con portada y etiquetas de álbum = nombre de playlist? ¿genera `.m3u8`? ¿corre cómodamente en la PC vieja (requiere Docker)? ¿está mantenido? Si cumple todo, \\\*\\\*detener este proyecto\\\*\\\* y usar Pinchflat. Si no, continuar. Registrar el resultado en `DECISIONS.md`.



\### Fase 1 — Núcleo de descarga (sin web)

\*\*Objetivo:\*\* desde la línea de comandos, dado un link de playlist de YouTube, descargar lo que falta como MP3.

\*\*Entregables:\*\*

\- `core/models.py`, `core/errors.py`, `core/sync\\\_rules.py` (calcular pendientes, umbral de seguridad RF-12).

\- `adapters/repo.py` con SQLite y migraciones.

\- `adapters/ytdlp\\\_source.py` (`inspect`, `list\\\_items` en modo "plano" sin descargar, `download` con \*progress hooks\*, límites de velocidad y pausas entre solicitudes, ffmpeg para MP3).

\- CLI mínima: `python -m playlist\\\_sync add <url>`, `sync <id>`, `status`.

\- Clasificación de errores de yt-dlp → códigos de 6.3.

\*\*Criterios de aceptación:\*\* con una playlist de prueba, la primera corrida descarga todo; la segunda no descarga nada; al agregar un video a la playlist y correr de nuevo, solo baja el nuevo; una URL de playlist privada devuelve `PRIVATE\\\_SOURCE` sin descargar.

\*\*Pruebas:\*\*

\- Unitarias de `sync\\\_rules` (incluida la regla de 0 elementos y < 50 %).

\- Unitarias de clasificación de errores con mensajes grabados.

\- Integración con un `FakeSource` (sin red).

\- Integración \*\*real\*\* marcada `@pytest.mark.network` (desactivada por defecto) con la playlist de prueba del dueño.

\*\*No hacer:\*\* nada de web, nada de podcasts, nada de `.m3u8` aún.



\### Fase 2 — Biblioteca (archivos, etiquetas y playlists)

\*\*Objetivo:\*\* que lo descargado quede ordenado y reconocible por cualquier reproductor.

\*\*Entregables:\*\* `adapters/library.py` (estructura de 6.2, etiquetas ID3 con mutagen, portada embebida, `cover.jpg`, `.m3u8` relativo y regenerable, saneado de nombres, manejo de colisiones).

\*\*Criterios de aceptación:\*\* una carpeta generada se abre en el reproductor del dueño mostrando álbum, orden y portada; reordenar la playlist remota cambia el `.m3u8` y la etiqueta de pista \*\*sin renombrar archivos\*\*; regenerar dos veces produce resultados idénticos.

\*\*Pruebas:\*\* leer etiquetas con mutagen y verificarlas; `.m3u8` con rutas relativas y UTF-8; nombres con caracteres inválidos/emoji/longitud extrema; idempotencia; prueba de que \*\*ningún\*\* código borra audio (buscar cualquier `unlink`/`remove` en pruebas de arquitectura).

\*\*No hacer:\*\* no tocar la API ni la UI.



\### Fase 3 — API y trabajos en segundo plano

\*\*Objetivo:\*\* exponer todo por HTTP con progreso en vivo.

\*\*Entregables:\*\* FastAPI con endpoints: `POST /sources`, `GET /sources`, `GET /sources/{id}`, `POST /sources/{id}/sync`, `POST /sync-all`, `POST /items/{id}/retry`, `GET /events` (SSE), `GET /health`. Ejecutor de trabajos con candado (RF-11), cola secuencial, cancelación segura, logs rotativos.

\*\*Criterios de aceptación:\*\* se puede agregar una fuente, lanzar sincronización y ver progreso por SSE; segundo `sync` simultáneo responde "ya hay una en curso"; los errores salen con código y mensaje de 6.3.

\*\*Pruebas:\*\* `TestClient` con `FakeSource`; prueba de concurrencia del candado; prueba de SSE (eventos en orden); validación de entrada (URLs inválidas, inyección de rutas).

\*\*No hacer:\*\* no construir la UI aún.



\### Fase 4 — Interfaz web "a prueba de mamá"

\*\*Objetivo:\*\* la pantalla única descrita en 1.3.

\*\*Entregables:\*\* `index.html`, `app.js`, `styles.css`, manifiesto PWA e íconos; tarjetas por fuente con portada, estado en palabras simples, botón grande "Actualizar", botón "Actualizar todo", caja "Pega un link o escribe el nombre de un podcast", lista de errores con botón "Reintentar", avance en vivo, modo oscuro automático.

\*\*Criterios de aceptación:\*\* usable con una mano en celular (ancho 360 px); contraste suficiente; sin jerga técnica; funciona como app instalada; un usuario no técnico completa "agregar playlist → actualizar → ver Al día ✓" sin ayuda (prueba manual).

\*\*Pruebas:\*\* pruebas automáticas de contrato de la API usada por la UI; lista de verificación manual en `docs/manual-checks.md` (agregar, privada, error, reintento, sin internet).

\*\*No hacer:\*\* no agregar frameworks de frontend ni paso de compilación.



\### Fase 5 — Podcasts

\*\*Objetivo:\*\* RF-13 y RF-14.

\*\*Entregables:\*\* `adapters/rss\\\_source.py` (feed → episodios, descarga directa con reanudación segura y verificación de tamaño), `adapters/itunes\\\_search.py` (búsqueda por nombre; verificar API vigente), soporte `kind=yt\\\_podcast`, orden más-nuevo-primero, género "Podcast", portada del programa. En la UI, la caja de búsqueda acepta nombre o link.

\*\*Criterios de aceptación:\*\* buscar un podcast por nombre, elegirlo, descargar episodios y verlos como una playlist en el reproductor; un feed caído da error claro.

\*\*Pruebas:\*\* feeds de ejemplo como \*fixtures\* (RSS válido, con enclosures raros, sin portada, con redirecciones); búsqueda con respuestas simuladas; episodios ya descargados no se repiten.

\*\*No hacer:\*\* no soportar podcasts con autenticación o de pago.



\### Fase 6 — Operación diaria

\*\*Objetivo:\*\* que funcione "solo" en la PC vieja.

\*\*Entregables:\*\* `start.bat` (y guía para ponerlo en el inicio automático de Windows o Programador de tareas), auto-actualización de yt-dlp al arrancar (RF-16), sincronización programada (RF-17) con intervalo configurable, respaldo automático de la base de datos, rotación de logs, `doctor` accesible desde la UI ("Revisar sistema").

\*\*Criterios de aceptación:\*\* tras reiniciar la PC, el servidor está disponible sin intervención; si falla la actualización de yt-dlp, la app sigue funcionando y lo informa; el respaldo se puede restaurar.

\*\*Pruebas:\*\* programador con reloj simulado; arranque con y sin internet; restauración de respaldo.

\*\*No hacer:\*\* no instalar servicios de Windows complejos ni requerir administrador si se puede evitar.



\### Fase 7 — Entrega a dispositivos y cierre

\*\*Objetivo:\*\* documentación y prueba de extremo a extremo.

\*\*Entregables:\*\* `docs/syncthing.md` (guía ilustrada en español: emparejar PC↔celular, carpeta "Enviar solamente" en la PC y "Recibir solamente" en el celular, excluir la app de ahorro de batería en Android, verificar qué app de Syncthing para Android está mantenida actualmente), guía de dispositivo nuevo, guía de solución de problemas, README final con instalación desde cero.

\*\*Criterios de aceptación (E2E manual):\*\* agrego una canción a una playlist de YouTube → abro la página → "Actualizar" → la canción aparece en el celular, en su playlist, con portada, sin tocar nada más; en un dispositivo nuevo, tras emparejar, se descarga toda la biblioteca en orden.

\*\*Pruebas:\*\* lista E2E completa en `docs/manual-checks.md` ejecutada y marcada; prueba automática E2E con `FakeSource` que cubre añadir → sincronizar → archivos+m3u8 correctos → segunda corrida sin cambios.



\---



\## 8. Estrategia de pruebas (transversal)



\- \*\*Pirámide:\*\* muchas unitarias en `core/`; integración con \*fakes\*; pocas pruebas reales con red (`@pytest.mark.network`, \*\*desactivadas por defecto\*\*, se corren a mano).

\- \*\*Sin red por defecto:\*\* las pruebas normales no llaman a YouTube ni a iTunes.

\- \*\*Fixtures reales grabadas:\*\* mensajes de error de yt-dlp, respuestas de iTunes, feeds RSS. Si YouTube cambia un mensaje, solo se actualiza la \*fixture\* y el mapeo.

\- \*\*Propiedades que SIEMPRE deben probarse:\*\* idempotencia de sincronización; incremental correcto; regla de seguridad (0 o < 50 %); nunca se borra audio; nombres de archivo seguros; `.m3u8` válido; etiquetas correctas; el candado de un solo trabajo.

\- \*\*Comandos estándar\*\* (documentarlos en README): `pytest`, `pytest --cov=src/playlist\\\_sync/core`, `ruff check .`, `ruff format --check .`, `mypy src/playlist\\\_sync/core`.

\- \*\*Regla:\*\* un \*bug\* corregido = una prueba nueva que lo reproduce.



\---



\## 9. Seguridad y robustez



\- Ejecutar yt-dlp \*\*por su API de Python\*\*; si en algún punto se llama a un proceso externo (ffmpeg), usar lista de argumentos, \*\*nunca\*\* `shell=True` ni concatenar texto del usuario.

\- Validar URLs: solo `http(s)`, dominios permitidos para `yt\\\_playlist` (`youtube.com`, `music.youtube.com`, `youtu.be`); feeds RSS solo `http(s)` y bloquear destinos de red interna (evitar SSRF desde la UI).

\- Sanear \*\*todo\*\* nombre de archivo y verificar que la ruta final quede dentro de `music\\\_root` (anti \*path traversal\*).

\- La app escucha en la red local \*\*sin autenticación\*\* (decisión consciente, uso doméstico): documentarlo con una advertencia clara en el README; por defecto, enlazar a `0.0.0.0` solo si el dueño lo confirma, si no `127.0.0.1`.

\- Respetar límites de velocidad y pausas entre solicitudes para no activar bloqueos.

\- Manejar disco lleno, nombres duplicados, cortes de internet a mitad de descarga (archivos `.part` limpiados sin tocar los completos).

\- No registrar en logs datos personales innecesarios.



\---



\## 10. Criterios de aceptación globales (el proyecto está "terminado" cuando…)



1\. Un usuario no técnico agrega una playlist pegando un link y ve su estado en palabras simples.

2\. "Actualizar" descarga solo lo nuevo; dos pulsaciones seguidas no repiten nada.

3\. Los MP3 tienen portada y etiquetas; el reproductor del dueño detecta cada playlist y su orden \*\*sin crearlas a mano\*\*.

4\. Los errores (privada, no disponible, sin internet…) se explican en español con qué hacer.

5\. Los podcasts (RSS y YouTube) funcionan como playlists de un solo programa.

6\. Tras reiniciar la PC vieja, todo vuelve a funcionar sin intervención y yt-dlp se mantiene actualizado.

7\. Un dispositivo nuevo recibe toda la biblioteca en orden siguiendo `docs/syncthing.md`.

8\. `pytest`, `ruff` y `mypy` pasan; cobertura de `core/` ≥ 80 %.

9\. Nunca se borra audio.



\---



\## 11. Lista de "NO HACER" (resumen anti-desvío)



\- ❌ No agregues Spotify, Tidal, cookies, login, nube, Docker obligatorio ni frameworks de frontend.

\- ❌ No borres archivos de música jamás.

\- ❌ No renombres archivos al reordenar una playlist.

\- ❌ No avances de fase sin aprobación.

\- ❌ No cambies el stack, las firmas de la sección 5.2 ni la estructura de 6.2 sin registrarlo y pedir aprobación.

\- ❌ No uses `shell=True`, no concatenes entradas del usuario en comandos.

\- ❌ No escribas mensajes de error técnicos para el usuario final.

\- ❌ No dejes funciones sin pruebas ni "TODO" sin anotar en `ideas-futuras.md`.



\---



\## 12. Protocolo de reporte al cerrar cada fase



Entrega \*\*exactamente\*\* esto y detente:



```

\\## Reporte de Fase N

\\- Resumen (3–5 líneas):

\\- Requisitos cubiertos (IDs RF/RNF):

\\- Criterios de aceptación: \\\[✔/✘] uno por uno

\\- Pruebas: cantidad, resultado, cobertura de core/

\\- Comandos para verificar (copiar/pegar):

\\- Decisiones nuevas (resumen de DECISIONS.md):

\\- Riesgos o dudas abiertas:

\\- Qué sigue (Fase N+1) y qué necesito del dueño:

```



\---



\## 13. Prompts listos para pegar



\### 13.1 Arranque (primera vez)

```

Lee PROMPT\\\_MAESTRO.md completo. Sigue estrictamente la sección 0.

Empieza por la Fase 0. Antes de escribir código, hazme las preguntas

de la tabla 1.4 que no puedas resolver tú (máx. 3 a la vez, con tu

opción recomendada). Al terminar la fase, entrega el Reporte de fase

(sección 12) y detente hasta que yo diga "aprobada".

```



\### 13.2 Continuar con la siguiente fase

```

La Fase N está aprobada. Relee PROMPT\\\_MAESTRO.md (secciones 0, 1, 2, 3

y la Fase N+1) y docs/DECISIONS.md. Implementa solo la Fase N+1 con sus

pruebas. No agregues nada fuera de alcance. Al final, entrega el

Reporte de fase y detente.

```



\### 13.3 Si la IA se desvía

```

Detente. Estás saliendo del alcance de PROMPT\\\_MAESTRO.md. Revierte lo

que no está en la fase actual, relee las secciones 0, 3 y 11, y dime

qué parte del plan estabas siguiendo al hacer esto.

```



\### 13.4 Si algo no funciona por cambios de YouTube

```

Diagnostica sin cambiar la arquitectura: 1) ejecuta doctor,

2\\) comprueba la versión de yt-dlp y actualízala, 3) captura el mensaje

de error real, 4) agrégalo como fixture y como prueba que falle,

5\\) corrige solo el adaptador afectado. Reporta antes de tocar algo más.

```

