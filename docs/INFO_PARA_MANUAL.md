# Ficha Técnica y Operativa Verificada para el Manual de Usuario — Playlist Sync

- **Commit exacto verificado (`git rev-parse --short HEAD`):** `5c72717` (`VERIFICADO` ejecutando `git rev-parse --short HEAD`, tags asociados: `fix-R6-completa`, `v1.0.1-audit-fixed`).
- **Fecha de verificación:** `2026-11-02`
- **Entorno donde se verificó:** Linux Mint `22.3 (Zena)` basado en Ubuntu `24.04 LTS (noble)`, con Python `3.12.3`, `ffmpeg 6.1.1-3ubuntu5`, `Node.js v18.19.1` y `yt-dlp 2026.10.26` + `yt-dlp-ejs 0.8.0` (`VERIFICADO` con `/etc/os-release` y `.venv/bin/python -m playlist_sync doctor`).

> **Convención de etiquetas de evidencia en este documento:**
> - **`VERIFICADO`**: Comprobado directamente leyendo el archivo y línea exactos del código o ejecutando el comando real en este equipo.
> - **`NO VERIFICADO`**: Deducido del código o del comportamiento estándar del sistema operativo sin haber disparado ese caso puntual en vivo.
> - **`NO VERIFICABLE AQUÍ`**: Requiere hardware externo (teléfono Android físico emparejado por Syncthing, otra PC con Windows 11 o reinicio completo sin sesión gráfica).

---

## Nota sobre Discrepancias Menores entre `README.md` y el Código Real (`VERIFICADO`)

Al contrastar `README.md` línea por línea contra el código fuente actual (`5c72717`), se detectaron únicamente estos matices menores que el redactor del manual debe conocer:
1. **`systemd/install-service.sh` copia vs. genera con `sed`:** `README.md:56` dice *"1. Copia la unidad de servicio `playlist-sync.service` a `~/.config/systemd/user/`"*, mientras que en realidad `systemd/install-service.sh:16-17` transforma la plantilla con `sed` sustituyendo `%h/playlist-sync` por la ruta real del repositorio (`REPO_DIR`) antes de escribir `~/.config/systemd/user/playlist-sync.service` (`VERIFICADO` en `systemd/install-service.sh:15-17`).
2. **Doble actualización de `yt-dlp` al arrancar:** `start.sh:11`, `start.bat:12` y `systemd/playlist-sync.service:11` ejecutan `pip install --upgrade --no-input "yt-dlp[default]"` antes de lanzar Python, y además `src/playlist_sync/main.py:447` vuelve a invocar `auto_update_ytdlp()` dentro de `serve` para dejar constancia en `playlist_sync.log` (`VERIFICADO` en `start.sh:11`, `start.bat:12`, `systemd/playlist-sync.service:11` y `src/playlist_sync/main.py:31-68,447`).
3. **Búsqueda por texto plano en CLI vs. Web:** En la interfaz web (`src/playlist_sync/web/app.js:426-464`), escribir un texto que no empieza por `http://` o `https://` abre una lista de hasta 8 resultados de iTunes (`GET /podcasts/search?q=...`) para que el usuario elija cuál agregar. En cambio, en el comando CLI `python -m playlist_sync add "texto"` (o si se envía texto sin `http` directo a `POST /sources`), `CompositeSource.inspect()` (`src/playlist_sync/adapters/composite_source.py:67-78`) busca en iTunes con `limit=1` y agrega automáticamente el primer podcast encontrado (`VERIFICADO` en `src/playlist_sync/web/app.js:448-464` y `src/playlist_sync/adapters/composite_source.py:67-78`).
4. **Opción `concurrency = 1` en `config.toml`:** `config.toml:26` y `README.md:214` muestran `concurrency = 1`. El código descarga siempre de forma secuencial (`1` a `1`) mediante un bucle `for` y un candado exclusivo `asyncio.Lock()`, pero no lee la clave `concurrency` desde `config.toml` (`VERIFICADO` en `src/playlist_sync/main.py:373-388` y `src/playlist_sync/services/sync.py:196`).

---

## 1. Qué es y qué NO hace

### Qué es (`VERIFICADO` en `README.md:1-4`, `PROMPT_MAESTRO.md:11-23`)
**Playlist Sync** es una aplicación web local y de línea de comandos (CLI) que corre en una computadora doméstica (PC con Linux Mint 22.3 / Ubuntu 24.04 o Windows 11) para descargar y mantener sincronizadas:
- **Playlists públicas o "No listadas" de YouTube y YouTube Music** (`yt_playlist`).
- **Podcasts por feed RSS** (`rss_podcast`), incluyendo búsqueda por nombre en el catálogo público de Apple/iTunes.
- **Podcasts alojados en YouTube** (`yt_podcast`).

Convierte todo el audio a archivos `.mp3`, les incrusta carátula frontal (`cover.jpg` / `APIC`) y etiquetas estándar `ID3v2.3` (título, artista, álbum, número de pista, género y fecha), y genera un archivo de lista de reproducción `.m3u8` con rutas relativas dentro de cada carpeta para que Syncthing lo copie al celular y cualquier reproductor móvil lo lea sin configuración manual (`VERIFICADO` en `src/playlist_sync/adapters/library.py:162-205,292-339`).

### Qué NO hace y limitaciones conocidas (`VERIFICADO` en `PROMPT_MAESTRO.md:201-215`, `README.md:7-23`)
1. **NO descarga playlists privadas ni contenido con inicio de sesión:** No usa cookies del navegador, ni cuentas de Google/YouTube, ni contraseñas (`VERIFICADO` en `src/playlist_sync/adapters/ytdlp_source.py:100-115` y `src/playlist_sync/core/errors.py:24`). Si una playlist es privada, muestra:
   `Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar.`
2. **NO descarga de Spotify, Apple Music, Tidal, Deezer ni Amazon Music:** Solo acepta dominios de YouTube (`youtube.com`, `www.youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtu.be`) y feeds RSS `http://` o `https://` públicos (`VERIFICADO` en `src/playlist_sync/adapters/ytdlp_source.py:24-30` y `src/playlist_sync/adapters/composite_source.py:55-79`).
3. **NO descarga videos con restricción de edad (+18) ni bloqueados geográficamente en tu país:** Los marca con error permanente no reintentable (`AGE_RESTRICTED` o `GEO_BLOCKED`) (`VERIFICADO` en `src/playlist_sync/core/errors.py:28-29` y `src/playlist_sync/core/sync_rules.py:17-25`).
4. **NO borra nunca archivos MP3 de tu disco (`RF-12`):** Si borras una canción de tu playlist en YouTube, Playlist Sync **conserva el archivo `.mp3` en tu carpeta**, lo marca como `removed_remote=1` en su base de datos y simplemente lo retira del archivo `.m3u8` (`VERIFICADO` en `src/playlist_sync/services/sync.py:187-189` y `src/playlist_sync/adapters/library.py:310`).
5. **NO tiene reproductor de música dentro de la página web:** La página web sirve para agregar listas, ver el estado y disparar descargas; la música se escucha en el reproductor del celular o de la PC (`VERIFICADO` en `src/playlist_sync/web/index.html`).
6. **Requiere que la PC esté encendida:** Como es un servidor 100 % local (sin nube), las descargas automáticas y la interfaz web solo funcionan mientras la computadora donde está instalado esté encendida (`VERIFICADO` en `README.md:15-18`).
7. **Regla estricta de un solo servidor activo a la vez:** Nunca deben ejecutarse dos instancias de Playlist Sync al mismo tiempo apuntando a la misma carpeta `music_root` (ni por red local ni por Syncthing). Cada PC tiene su propia base de datos `playlist_sync.sqlite3` (`VERIFICADO` en `README.md:15-18`).
8. **Aviso legal y de uso personal (`VERIFICADO` literal de `README.md:9`):**
   > *"Este proyecto ha sido desarrollado exclusivamente para **uso personal y educativo**. La descarga de audio de plataformas como YouTube puede infringir los términos de servicio del proveedor de contenido. Esta herramienta no facilita la distribución pública ni la compartición de material con derechos de autor."*

---

## 2. Requisitos Previos y Versiones

### Requisitos verificados en código (`VERIFICADO` en `src/playlist_sync/doctor.py:88-259`, `pyproject.toml:10`)
| Componente | Requisito / Versión | Carácter | Para qué sirve |
|---|---|---|---|
| **Sistema Operativo** | **Linux Mint 22.3** (Ubuntu 24.04 LTS `noble`) o **Windows 11** | Requerido (`VERIFICADO`) | Sistema base donde corre el servidor. |
| **Python** | **`>= 3.12`** (en este equipo: `3.12.3`) | **REQUERIDO** (`critical=True` en `doctor.py:96`) | Ejecuta el servidor FastAPI, la base de datos SQLite y la lógica de sincronización. |
| **ffmpeg** | Cualquier versión funcional en `PATH` (en este equipo: `6.1.1-3ubuntu5`) | **REQUERIDO** (`critical=True` en `doctor.py:138`) | Extrae y convierte el audio de YouTube y de podcasts (`.m4a`/`.ogg`) a `.mp3` a `192 kbps`, y convierte portadas WebP a JPEG. |
| **Deno** (o **Node.js**) | Deno en `~/.deno/bin/deno` o `/usr/bin/deno` (o `node` en `PATH`) | **OPCIONAL en `doctor` pero necesario para retos JS de YouTube** (`critical=False` en `doctor.py:167`) | Permite a `yt-dlp` + `yt-dlp-ejs` resolver los desafíos de firma JavaScript de YouTube sin bloqueos. |
| **yt-dlp + yt-dlp-ejs** | `yt-dlp[default]>=2025.2.19` (en este equipo: `yt-dlp==2026.10.26`, `yt-dlp-ejs==0.8.0`) | **REQUERIDO** (`critical=True` en `doctor.py:201`) | Motor de extracción de listas y audio de YouTube / YouTube Music. |
| **Espacio en disco** | Mínimo **1024 MB (1 GB)** libres por defecto (configurable con `min_disk_free_mb`) | **REQUERIDO** (`critical=True` en `doctor.py:222`) | Antes de descargar, verifica que haya al menos `min_disk_free_mb` libres; si no, aborta con `DISK_FULL`. |

### Qué trae Linux Mint 22.3 de fábrica y qué instala `install.sh` (`VERIFICADO` en `install.sh:9-26` y `/etc/os-release`)
- **Ya viene preinstalado en Linux Mint 22.3:** `python3` (`3.12.3`) y herramientas básicas del sistema (`systemd`, `sed`, `ip`).
- **Lo que instala `install.sh` automáticamente si falta:**
  - Con `sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl`: instala el módulo `python3-venv` (indispensable en Ubuntu 24.04 / Mint 22.3 por la restricción PEP 668 que impide usar `pip` fuera de un entorno virtual), `python3-pip`, `ffmpeg` y `curl`.
  - Con `curl -fsSL https://deno.land/install.sh | sh`: instala **Deno** en `~/.deno/bin/deno` si `deno` no está ya en el `PATH`.
  - Dentro de `.venv`: instala `playlist-sync` y todas sus dependencias Python (`fastapi`, `uvicorn`, `yt-dlp[default]`, `mutagen`, `httpx`, `defusedxml`, `pydantic`).

---

## 3. Instalación desde Cero

### 3.1 En Linux Mint 22.3 / Ubuntu 24.04 LTS (`VERIFICADO` en `README.md:41-46` e `install.sh:1-45`)

Ejecuta estos comandos en la terminal, en este orden exacto:

```bash
git clone <url-del-repo> playlist-sync
cd playlist-sync
chmod +x install.sh start.sh systemd/install-service.sh
./install.sh
```

**Qué hace `./install.sh` paso a paso y qué salida muestra (`VERIFICADO` en `install.sh:4-44`):**
1. Imprime la cabecera:
   ```text
   ==================================================
    Playlist Sync — Instalador para Linux (Mint / Ubuntu)
   ==================================================
   [1/5] Verificando e instalando paquetes del sistema (apt)...
   ```
   Te pedirá tu contraseña de `sudo` para ejecutar `sudo apt-get update -y` y `sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl`.
2. Verifica o instala Deno:
   ```text
   [2/5] Verificando runtime Deno...
   ```
   Si ya está instalado muestra `Deno ya está instalado.`; si no, muestra `Instalando Deno con el instalador oficial...` y lo descarga en `$HOME/.deno/bin`.
3. Crea el entorno virtual `.venv`:
   ```text
   [3/5] Configurando entorno virtual (.venv)...
   ```
4. Instala las dependencias Python dentro de `.venv`:
   ```text
   [4/5] Instalando dependencias de Python dentro del venv...
   ```
5. Ejecuta el diagnóstico automático (`doctor`):
   ```text
   [5/5] Ejecutando verificación del sistema (doctor)...
   ```
   Y termina con el mensaje literal:
   ```text
   ¡Instalación completada! Puedes iniciar la aplicación con ./start.sh
   ```

**Cómo saber que salió bien (`VERIFICADO` ejecutando `.venv/bin/python -m playlist_sync doctor`):**
En la salida del paso `[5/5]`, las 6 comprobaciones deben mostrar `[OK]` y al final debe aparecer la frase exacta:
```text
El sistema cumple con los requisitos necesarios para operar.
```

---

### 3.2 En Windows 11 (`VERIFICADO` en `README.md:70-74` e `install.ps1:1-57`; ejecución real en Windows 11: `NO VERIFICABLE AQUÍ` por estar en Linux Mint)

1. Abre **PowerShell** dentro de la carpeta del proyecto `playlist-sync` y ejecuta:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1
   ```
2. **Qué hace `install.ps1` y qué muestra en pantalla (`VERIFICADO` en `install.ps1:4-56`):**
   - `[1/5] Verificando Python...`: Busca `py -3.12` o `python`. Si no existe, lo instala automáticamente con `winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements`.
   - `[2/5] Verificando ffmpeg...`: Si no encuentra `ffmpeg`, lo instala con `winget install --id Gyan.FFmpeg --exact --source winget --accept-package-agreements --accept-source-agreements` y muestra:
     `Aviso: Puede requerir reiniciar la terminal para actualizar el PATH.`
   - `[3/5] Verificando runtime Deno...`: Si no encuentra `deno`, lo instala con `winget install --id DenoLand.Deno --exact --source winget --accept-package-agreements --accept-source-agreements`.
   - `[4/5] Configurando entorno virtual (.venv)...`: Ejecuta `& $pythonExe @pythonArgs -m venv .venv` e instala los paquetes con `.\.venv\Scripts\pip.exe`.
   - `[5/5] Ejecutando verificación del sistema (doctor)...`: Ejecuta `.\.venv\Scripts\python.exe -m playlist_sync.doctor`.
   - Al finalizar con éxito muestra en verde:
     ```text
     Instalación completada. Puedes iniciar la aplicación con .\start.bat
     ```

---

## 4. Primer Arranque, Acceso desde el Celular y Seguridad en Red Local

### 4.1 Cómo iniciar el servidor a mano (`VERIFICADO` en `start.sh:1-18`, `start.bat:1-24`, `src/playlist_sync/main.py:429-462`)
- **En Linux Mint:**
  ```bash
  ./start.sh
  ```
  *(O directamente: `.venv/bin/python -m playlist_sync serve`)*
  Salida literal en consola:
  ```text
  [1/2] Verificando actualización del motor de descargas (RF-16)...
  [2/2] Iniciando Playlist Sync...
  Iniciando Playlist Sync en http://127.0.0.1:8000
  ```
- **En Windows 11:**
  ```cmd
  start.bat
  ```
  *(O directamente: `.venv\Scripts\python.exe -m playlist_sync serve`)*
  Salida literal en consola:
  ```text
  [1/2] Verificando actualizacion del motor de descargas (RF-16)...
  [OK] Motor yt-dlp al dia.
  [2/2] Iniciando Playlist Sync...
  Iniciando Playlist Sync en http://127.0.0.1:8000
  ```

### 4.2 Cómo detener el servidor cuando se inició a mano (`VERIFICADO`)
En la ventana de terminal o símbolo del sistema donde está corriendo, presiona **`Ctrl + C`**.

### 4.3 En qué dirección y puerto queda por defecto (`VERIFICADO` en `config.toml:3-5` y `src/playlist_sync/main.py:436-437`)
- **Dirección (host) por defecto:** `127.0.0.1` (solo accesible desde la misma PC como `http://localhost:8000` o `http://127.0.0.1:8000`).
- **Puerto por defecto:** `8000`.

### 4.4 Cómo abrirlo desde el celular en la misma red Wi-Fi (`VERIFICADO` en `README.md:95-102` y `src/playlist_sync/main.py:359-361`)
1. **Habilitar escucha en red local (`0.0.0.0`):**
   - **Opción permanente (recomendada):** Abre el archivo `config.toml` y en la sección `[server]` cambia:
     ```toml
     [server]
     host = "0.0.0.0"
     port = 8000
     ```
     Si usas el servicio automático en Linux Mint, reinícialo con:
     ```bash
     systemctl --user restart playlist-sync.service
     ```
   - **Opción temporal por comando:**
     ```bash
     ./start.sh serve --host 0.0.0.0 --port 8000
     ```
2. **Conocer la dirección IP local de la PC:**
   - **En Linux Mint:** Ejecuta `hostname -I` o `ip -4 addr` (busca la IP que empieza por `192.168.x.x` o `10.x.x.x`).
   - **En Windows 11:** Ejecuta `ipconfig` en PowerShell o CMD y busca `Dirección IPv4` (ej. `192.168.1.50`).
3. **Permitir el puerto `8000` en el firewall si está activo (`NO VERIFICADO` en firewall del usuario):**
   - **En Linux Mint (UFW):** Si tienes el cortafuegos UFW activado, permite el puerto 8000 en tu red local con:
     ```bash
     sudo ufw allow 8000/tcp
     ```
   - **En Windows 11:** Cuando aparezca la ventana del Firewall de Windows Defender al iniciar Python/Uvicorn, marca **"Redes privadas"** y pulsa **Permitir acceso**.
4. **Abrir en el celular:**
   Con el celular conectado al mismo Wi-Fi de casa, abre Chrome/Firefox y entra a:
   ```text
   http://<IP-DE-TU-PC>:8000
   ```
   *(Ejemplo: `http://192.168.1.50:8000`)*.

### 4.5 Advertencia de seguridad en red local (`VERIFICADO` literal de `README.md:101`)
> **⚠️ Advertencia de seguridad en red local:** Playlist Sync está diseñado para operar dentro de una red doméstica de confianza y **no incluye autenticación de usuarios**. Expón `0.0.0.0` únicamente en tu Wi-Fi privado de casa; nunca expongas el puerto `8000` a internet público ni en redes Wi-Fi abiertas.

---

## 5. Arranque Automático

### 5.1 En Linux Mint 22.3 con `systemd --user` (`VERIFICADO` en `systemd/install-service.sh:1-38` y `systemd/playlist-sync.service:1-22`)

Para que Playlist Sync arranque solo cada vez que se enciende la PC (incluso antes de que alguien inicie sesión gráfica) y se reinicie automáticamente si se cierra:

1. **Instalar y activar el servicio:**
   ```bash
   ./systemd/install-service.sh
   ```
2. **Salida esperada al instalar (`VERIFICADO` en `systemd/install-service.sh:10-38`):**
   ```text
   === Instalando servicio de usuario de Playlist Sync en Linux Mint ===
   Configurando ruta del repositorio: /home/<tu_usuario>/.../playlist-sync...
   Habilitando lingering para el usuario actual (<tu_usuario>)...
   Habilitando y arrancando servicio...

   [OK] Servicio instalado e iniciado con éxito.
   Para verificar el estado ejecuta: systemctl --user status playlist-sync.service
   Para ver los registros en tiempo real: journalctl --user -u playlist-sync.service -f
   ```
3. **Qué configuró internamente la unidad `~/.config/systemd/user/playlist-sync.service` (`VERIFICADO` en `systemd/playlist-sync.service:7-21`):**
   - `WorkingDirectory`: La ruta absoluta real de tu carpeta del proyecto.
   - `ExecStartPre`: `-%h/.../.venv/bin/pip install --upgrade --no-input "yt-dlp[default]"` (el guion `-` inicial hace que si no hay internet al encender la PC, `systemd` ignore el fallo de actualización y arranque el servidor de todos modos).
   - `ExecStart`: `%h/.../.venv/bin/python -m playlist_sync.main serve`.
   - `Restart=always` y `RestartSec=10`: Si el proceso cae, se levanta solo tras 10 segundos.
   - `Environment="PATH=%h/.deno/bin:/usr/local/bin:/usr/bin:/bin"`: Garantiza que `yt-dlp` encuentre Deno en `~/.deno/bin`.
   - `loginctl enable-linger <usuario>`: Permite que el servicio corra al encender la PC sin necesidad de iniciar sesión en el escritorio.
4. **Comandos para administrar y verificar el servicio (`VERIFICADO` en `README.md:60-65`):**
   - **Ver si está activo (`active (running)`):**
     ```bash
     systemctl --user status playlist-sync.service
     ```
   - **Verificar que `linger` está activado (`Linger=yes`):**
     ```bash
     loginctl show-user "$USER" -p Linger
     ```
   - **Ver los registros (logs) en vivo:**
     ```bash
     journalctl --user -u playlist-sync.service -f
     ```
   - **Reiniciar el servicio (por ejemplo, tras editar `config.toml`):**
     ```bash
     systemctl --user restart playlist-sync.service
     ```
   - **Detener el servicio:**
     ```bash
     systemctl --user stop playlist-sync.service
     ```

### 5.2 En Windows 11 (`VERIFICADO` en `README.md:81-85`)
1. Presiona las teclas **`Win + R`**, escribe `shell:startup` y presiona **Enter** (se abrirá la carpeta *Inicio* de tu usuario).
2. Haz clic derecho sobre `start.bat` en la carpeta del proyecto, elige **Crear acceso directo** y mueve ese acceso directo dentro de la carpeta `shell:startup`.

---

## 6. Recorrido de la Interfaz Web Pantalla por Pantalla (`VERIFICADO` en `src/playlist_sync/web/index.html` y `src/playlist_sync/web/app.js`)

Toda la aplicación cabe en **una sola pantalla** (`<title>Mi Música</title>`). A continuación se listan **todos los textos literales** que existen en `index.html` y `app.js`, organizados por sección y por estado:

### 6.1 Cabecera Superior (`.app-header`, `index.html:17-42`)
| Elemento | Texto literal exacto | Qué hace al pulsarlo |
|---|---|---|
| **Título principal** (`h1.header-title`) | `Mi Música` | Encabezado fijo de la página. |
| **Subtítulo** (`p.header-subtitle`) | `Listas y canciones para tu celular` | Descripción bajo el título. |
| **Botón secundario** (`#btn-reconcile`) | `Verificar archivos` (`aria-label="Verificar archivos ya descargados en disco"`) | Llama a `POST /reconcile` (`app.js:554-562`). Escanea `music_root` buscando archivos `[{external_id}].mp3` existentes en disco, los marca como descargados, regenera los `.m3u8`, recarga las tarjetas y muestra la notificación flotante: `Reconciliación completada: X archivos vinculados en disco.` (o `No se pudo verificar los archivos en disco.` si falla). |
| **Botón principal grande** (`#btn-sync-all`) | `Actualizar todo` (`aria-label="Actualizar todas las listas"`) | Llama a `POST /sync-all` (`app.js:540-552`). Si ya hay una descarga activa, muestra el toast `Ya hay una descarga en curso. Espera a que termine.`. Si está libre, inicia la revisión de todas las fuentes una por una y muestra el toast `Revisando todas tus listas...`. |

### 6.2 Banner Global de Descarga Activa (`#sync-banner`, `index.html:45-56` y `app.js:161-253`)
Permanece oculto (`class="sync-banner hidden"`) mientras no hay descargas. Cuando se inicia una sincronización, aparece en azul en la parte superior con un icono giratorio (`spinner`) y una barra de progreso:
- **Al iniciar la descarga de una lista (`evento SSE sync_started`, `app.js:165`):**
  - Título (`#sync-banner-title`): `Descargando música...`
  - Detalle (`#sync-banner-detail`): `Iniciando descarga de canciones`
  - Barra (`#sync-banner-progress`): `0%`
- **Al iniciar "Actualizar todo" (`evento SSE sync_all_started`, `app.js:217`):**
  - Título: `Actualizando todas las listas...`
  - Detalle: `Procesando una por una`
  - Barra: `0%`
- **Durante la descarga de cada canción (`evento SSE progress`, `app.js:169-184`):**
  - Título: `Descargando X de Y: <Título de la canción>` (por ejemplo: `Descargando 2 de 5: Queen - Bohemian Rhapsody`). Si no hubiera índice, muestra `Descargando: <Título de la canción>` (o `Canción actual` si aún no hay título).
  - Detalle: `Progreso: <porcentaje>%` (por ejemplo: `Progreso: 45.2%`).
  - Barra: Ancho dinámico de `0%` a `100%`.
- **Al terminar (`sync_completed` o `sync_all_completed` o `sync_failed`):**
  - El banner se oculta automáticamente y aparece una notificación flotante (toast) en la parte inferior:
    - Si descargó canciones nuevas (`data.downloaded > 0`): `¡Listo! Se descargaron X canciones nuevas.` (`app.js:188`)
    - Si no había canciones nuevas (`data.downloaded === 0`): `La lista ya estaba al día.` (`app.js:189`)
    - Si terminó `Actualizar todo`: `¡Se revisaron todas tus listas con éxito!` (`app.js:225`)
    - Si falló la sincronización de una lista: muestra el mensaje de error en español enviado por el servidor (ej. `Esta playlist es privada...`) o el respaldo `Hubo un problema al sincronizar la lista.` (`app.js:199-211`).

### 6.3 Caja para Agregar Listas o Podcasts (`.add-section`, `index.html:59-92` y `app.js:415-524`)
| Elemento | Texto literal exacto | Comportamiento |
|---|---|---|
| **Etiqueta del campo** (`label[for="source-url-input"]`) | `Agregar una lista o programa` | Etiqueta superior del formulario. |
| **Campo de texto** (`#source-url-input`) | Placeholder: `Pega un link o escribe el nombre de un podcast` | Acepta un link `http://` o `https://` (YouTube, YouTube Music o feed RSS) o bien palabras para buscar un podcast por nombre. |
| **Botón de envío** (`#btn-add-source`) | Estado normal: `Guardar`<br>Si pegaste un link: `Guardando...`<br>Si escribiste un nombre: `Buscando...` | Se deshabilita mientras procesa la petición y vuelve a `Guardar` al terminar (`app.js:429,446,450,462`). |
| **Recuadro de error** (`#add-error-box`) | Oculto por defecto. Muestra el texto del error (ej. `Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar.`) y un botón de cierre `&times;` (`aria-label="Cerrar aviso"`). | Al pulsar `&times;` (`#btn-close-error`), se oculta el aviso (`app.js:644-647`). |
| **Panel de resultados de búsqueda de podcasts** (`#podcast-search-results`) | Encabezado: `Podcasts encontrados:` con botón `&times;` (`#btn-close-search`, `aria-label="Cerrar"`).<br>Cada fila muestra portada, título, `<artista> · <N> episodios` y el botón `Agregar` (que cambia a `Guardando...` al pulsarlo). | Al pulsar `Agregar` en un resultado, registra el feed RSS, cierra la lista de búsqueda, muestra el toast `¡"<Título>" guardado!` e inicia la descarga (`app.js:494-517`). |

### 6.4 Barra de Salud del Sistema y Estado de Conexión (`.system-bar`, `index.html:95-104` y `app.js:102-114,599-635`)
1. **Botón de Salud del Sistema (`#system-health-pill`):**
   - Mientras carga al abrir la página: `Verificando sistema...` (`index.html:98`)
   - Cuando todas las comprobaciones críticas pasan (`status === 'ok'`): punto verde + `Sistema listo ✓` (`app.js:606`)
   - Cuando falla alguna comprobación crítica (`status === 'degraded'`): punto ámbar + `Atención necesaria ⚠️` (`app.js:606`)
   - Si el servidor está apagado o inalcanzable: punto ámbar + `Servidor inaccesible` (`app.js:613`)
   - **Qué pasa al pulsarlo (con clic o con teclado `Tab` + `Enter`/`Espacio`):** Abre la ventana modal **`Estado del Sistema`** (`#health-modal`, `index.html:123-136`) que lista cada componente (`Python`, `ffmpeg`, `Runtime JS (Deno/Node)`, `yt-dlp`, `Espacio en disco`, `Permisos de escritura`) con la etiqueta verde `Listo ✓` o roja `Falta ✗`, su detalle y su recomendación. Se cierra pulsando el botón `Entendido` (`#btn-modal-dismiss`) o la `×` (`#btn-close-modal`).
2. **Píldora de Conexión (`#connection-pill`):**
   - Conexión SSE activa: punto verde brillante + `En vivo` (`app.js:108`)
   - Si el canal SSE se corta temporalmente: punto ámbar + `Respaldo (5s)` (consulta automáticamente `/sources` y `/health` cada 5 segundos, `app.js:110,116-127`)
   - Si el servidor deja de responder durante el respaldo: punto rojo + `Sin conexión` (`app.js:112`)

### 6.5 Área Principal de Listas (`#sources-container`, `index.html:108-119` y `app.js:257-399`)

- **Estado 0 — Cargando inicialmente (`index.html:116-117`):**
  - Título: `Cargando tus listas...`
  - Subtítulo: `Un momento por favor.`
- **Estado 1 — Sin fuentes registradas (`state.sources.length === 0`, `app.js:260-272`):**
  - Título: `No tienes listas guardadas`
  - Subtítulo: `Pega un enlace de YouTube o YouTube Music arriba para empezar a guardar tu música.`
- **Estado 2 — Con fuentes registradas (tarjetas `.source-card`, `app.js:277-376`):**
  Cada tarjeta muestra la portada (`/covers/{id}` o el icono musical por defecto si no hay portada), el título de la lista (`h2.source-title`), **una insignia de estado**, el contador **`X de Y listas`** (`app.js:303`) y dos botones de acción:

  **Insignias posibles en la tarjeta (en orden exacto de prioridad según `app.js:287-300`):**
  1. **Sincronizando esta fuente ahora mismo:** insignia azul `Descargando...` (`.badge-active`)
  2. **La fuente tuvo un error global (`source.status === 'error'`):** insignia roja `Hubo un problema` (`.badge-error`) + texto rojo debajo con el mensaje exacto de `source.last_error_message` (ej. `La playlist apareció vacía o con muchas menos canciones. No cambié nada por seguridad.`). **Nunca muestra `Al día ✓` si hay error.**
  3. **Hay canciones individuales con error (`source.error_count > 0`):**
     - Si es 1 canción: insignia ámbar `Problemas en 1 canción` (`.badge-warning`)
     - Si son 2 o más: insignia ámbar `Problemas en X canciones` (`.badge-warning`)
  4. **Hay canciones pendientes por descargar (`source.pending_count > 0`):** insignia ámbar `X nuevas — Descargar` (`.badge-warning`)
  5. **Todo descargado y sin errores:** insignia verde `Al día ✓` (`.badge-success`)

  **Botones dentro de cada tarjeta (`app.js:350-370`):**
  1. **Botón primario (`.btn-sync-source`):**
     - Texto cuando `pending_count > 0`: `Descargar nuevas`
     - Texto cuando `pending_count === 0`: `Actualizar`
     - Si hay cualquier descarga en curso (`state.isSyncing === true`), el botón aparece **deshabilitado (`disabled`)**.
     - Al pulsarlo: llama a `POST /sources/{id}/sync` y muestra el toast `Descarga iniciada...`.
  2. **Botón secundario (`.btn-toggle-items`):**
     - Texto cerrado: `Ver canciones`
     - Texto abierto: `Ocultar canciones`
     - Al pulsarlo: despliega el panel `.source-items-panel`. Mientras consulta `GET /sources/{id}` muestra `Cargando canciones...`. Luego lista cada canción con su título y a la derecha:
       - Si `status === 'downloaded'`: marca verde `✓`
       - Si `status === 'pending'`: texto gris `Pendiente`
       - Si `status === 'downloading'`: texto azul `Descargando`
       - Si `status === 'error'`: debajo del título muestra en rojo el motivo (`it.error_message` o `No se pudo descargar`) y a la derecha el botón **`Reintentar`** (`.btn-retry-item`).

---

## 7. Flujos Paso a Paso con lo que Ve el Usuario (`VERIFICADO` en `src/playlist_sync/web/app.js`)

### a) Agregar una playlist de YouTube o YouTube Music
1. El usuario copia el enlace de una playlist pública (ej. `https://music.youtube.com/playlist?list=PL...`) y lo pega en el cuadro `Pega un link o escribe el nombre de un podcast`.
2. Pulsa el botón **`Guardar`**.
3. El botón cambia a **`Guardando...`** y se deshabilita unos segundos mientras el servidor consulta el título, la portada y la lista de canciones en YouTube sin descargar aún el audio (`add_source_service`, `src/playlist_sync/services/sync.py:38-95`).
4. El campo de texto se limpia, aparece el mensaje flotante **`¡"<Nombre de la playlist>" guardada!`**, se dibuja la tarjeta con la insignia ámbar **`N nuevas — Descargar`** y **`0 de N listas`**, e inmediatamente comienza la descarga automática (`handleSyncSource(newSource.id)`, `app.js:441`) mostrando el toast **`Descarga iniciada...`**.

### b) Actualizar una fuente individual y usar "Actualizar todo"
- **Actualizar una sola fuente:** En la tarjeta de la playlist, pulsa **`Actualizar`** (o **`Descargar nuevas`**). Aparece el toast **`Descarga iniciada...`**, la insignia de la tarjeta cambia a **`Descargando...`** y el banner azul superior muestra el avance canción por canción. Al terminar, aparece **`¡Listo! Se descargaron X canciones nuevas.`** (o **`La lista ya estaba al día.`**) y la insignia queda en **`Al día ✓`**.
- **Actualizar todas las fuentes (`Actualizar todo`):** Pulsa el botón azul superior **`Actualizar todo`**. Aparece el toast **`Revisando todas tus listas...`** y el banner azul muestra **`Actualizando todas las listas...`** / **`Procesando una por una`**. Recorre todas las fuentes en orden; al terminar todas, muestra **`¡Se revisaron todas tus listas con éxito!`**.

### c) Agregar un podcast buscando por nombre y por link RSS
- **Buscando por nombre:**
  1. Escribe el nombre del programa (ej. `Radio Ambulante`) en el cuadro de texto (sin `http://`) y pulsa **`Guardar`**.
  2. El botón cambia a **`Buscando...`**.
  3. Debajo aparece el cuadro **`Podcasts encontrados:`** con hasta 8 programas del catálogo de iTunes, mostrando portada, nombre, autor y cantidad de episodios (`app.js:467-492`). (Si no hay coincidencias, muestra el recuadro rojo: `No se encontró ningún podcast con el nombre "<texto>".`).
  4. Pulsa el botón **`Agregar`** junto al podcast deseado. El botón cambia a **`Guardando...`**, se cierra la lista de búsqueda, aparece el toast **`¡"<Título>" guardado!`** y comienza la descarga de episodios.
- **Pegando directamente el link RSS (`https://...`):**
  1. Pega la URL del feed RSS en el cuadro de texto y pulsa **`Guardar`**.
  2. El flujo es idéntico al de una playlist: el botón dice **`Guardando...`**, valida que el XML sea un feed `<rss>` o `<feed>` seguro, crea la tarjeta y lanza la descarga.

### d) Agregar un podcast de YouTube
1. Pega la URL de la playlist o serie de podcast de YouTube (`https://www.youtube.com/playlist?list=...`) y pulsa **`Guardar`**.
2. `YtDlpSource.inspect()` detecta automáticamente si el título o la URL contiene la palabra `podcast` (`SourceKind.YT_PODCAST`, `src/playlist_sync/adapters/ytdlp_source.py:130-137`), le asigna el género ID3 `Podcast` y ordena su archivo `.m3u8` del episodio más nuevo al más antiguo.

### e) Reintentar una canción con error
1. Cuando una tarjeta muestra la insignia ámbar **`Problemas en 1 canción`** (o **`Problemas en X canciones`**), pulsa el botón **`Ver canciones`** de esa tarjeta.
2. En la lista desplegada, localiza la fila resaltada en rojo suave (`.item-error`), lee el motivo debajo del título (por ejemplo: `No hay conexión a internet.` o `YouTube pidió esperar un poco. Intenta de nuevo en unos minutos.`) y pulsa el botón **`Reintentar`**.
3. Si hay otra descarga corriendo en ese instante, muestra el toast **`Hay una descarga en curso. Espera a que termine antes de reintentar.`** y no altera nada (`app.js:584-586`).
4. Si el servidor está libre, reinicia el contador de intentos de esa canción a `0` (`reset_attempts=True`), la pasa a `pending`, muestra el toast **`Reintentando descarga...`** y arranca de inmediato la sincronización de esa lista (`src/playlist_sync/services/jobs.py:159-185`).

### f) Ver el progreso en vivo
Mientras cualquier descarga está activa:
1. El banner azul superior (`#sync-banner`) muestra el texto **`Descargando X de Y: <Título de la canción>`** y **`Progreso: <porcentaje>%`**, moviendo la barra blanca de `0%` a `100%` en tiempo real vía Server-Sent Events (`/events`).
2. Si por algún motivo se interrumpe el canal SSE en el navegador del celular, la píldora superior derecha cambia sola de **`En vivo`** a **`Respaldo (5s)`** y refresca las tarjetas cada 5 segundos sin que el usuario tenga que recargar la página.

---

## 8. Catálogo Completo de Errores (`VERIFICADO` en `src/playlist_sync/core/errors.py:8-42` y `src/playlist_sync/core/sync_rules.py:17-35`)

Todos los errores técnicos se traducen a códigos normalizados. El detalle técnico crudo (`technical_detail`) se guarda únicamente en `playlist_sync.log` y **nunca** se envía en las respuestas JSON al navegador (`VERIFICADO` en `src/playlist_sync/api/app.py:92-111`).

| Código (`ErrorCode`) | Mensaje literal exacto por defecto (`ERROR_MESSAGES`) | ¿Reintentable automáticamente? | Causa probable | Qué debe hacer el usuario |
|---|---|---|---|---|
| `PRIVATE_SOURCE` | `Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar.` | **No** | La playlist en YouTube está configurada como "Privada" o requiere iniciar sesión. | Entrar a YouTube, editar la visibilidad de la playlist a **Pública** o **No listada** y volver a guardarla/actualizarla. |
| `SOURCE_NOT_FOUND` | `No encontré esa playlist. Revisa que el link esté completo.` *(En búsqueda iTunes sin resultados por CLI: `No se encontró ningún podcast con el nombre '<texto>'.`; en 404 de fuente/ítem: `No se encontró la fuente solicitada.` / `El elemento solicitado no existe.`)* | **No** | El link está cortado, la playlist fue borrada de YouTube o el feed RSS devuelve 404. | Verificar el enlace en el navegador y pegarlo completo. |
| `INVALID_URL` | `Ese link no parece de YouTube ni de un podcast.` *(Variantes específicas en `rss_source.py` / `url_security.py`: `La dirección proporcionada no parece ser un feed RSS o Atom válido.`, `El enlace debe comenzar con http:// o https://.`, `Por seguridad, no se permite conectar a direcciones de red local o privada.`)* | **No** | Se pegó un enlace de otro sitio (ej. Spotify), un archivo que no es XML/RSS o una IP privada/local. | Pegar únicamente un enlace público de YouTube, YouTube Music o un feed RSS válido. |
| `ITEM_UNAVAILABLE` | `Este video ya no está disponible.` | **Sí** (hasta `max_retries = 3`) | El autor borró el video individual, lo puso en privado o reclamó derechos de autor. | Ninguna acción necesaria: el resto de la lista se descarga normal. Si fue un fallo temporal, se puede pulsar `Reintentar`. |
| `AGE_RESTRICTED` | `Este video tiene restricción de edad y no se puede descargar.` | **No** | YouTube exige cuenta mayor de 18 años logueada para ver ese video. | Como Playlist Sync no usa cuentas ni cookies por seguridad, ese video no puede descargarse. |
| `GEO_BLOCKED` | `Este video no está disponible en tu país.` | **No** | La discográfica o el canal bloqueó el video en tu región geográfica. | Buscar una versión alternativa de la canción en YouTube y agregarla a tu playlist. |
| `RATE_LIMITED` | `YouTube pidió esperar un poco. Intenta de nuevo en unos minutos.` | **Sí** (con espera exponencial creciente: `1s`, `2s`, `4s`...) | Se hicieron demasiadas descargas seguidas y YouTube activó un límite temporal (HTTP 429). | Esperar unos minutos y pulsar `Actualizar` (o aumentar `sleep_interval` en `config.toml`). |
| `NETWORK` | `No hay conexión a internet.` *(En descarga RSS truncada tras agotar reintentos: `La descarga del episodio quedó incompleta (se recibieron X de Y bytes).`)* | **Sí** (con espera exponencial creciente) | Corte de Wi-Fi/internet, fallo de DNS o el servidor del podcast cerró la conexión antes de enviar todo el archivo. | Comprobar la conexión a internet de la PC y pulsar `Actualizar` o `Reintentar`. |
| `DISK_FULL` | `No hay espacio en el disco.` | **No** | El espacio libre en la partición donde está `music_root` cayó por debajo de `min_disk_free_mb` (`1024 MB` por defecto). | Liberar espacio en el disco duro de la PC o reducir `min_disk_free_mb` en `config.toml`. |
| `TOOL_MISSING` | `Falta un programa necesario ({nombre}). Ejecuta la revisión del sistema.` *(Ej.: `Falta un programa necesario (ffmpeg). Ejecuta la revisión del sistema.`)* | **No** | `ffmpeg` o `yt-dlp` no están instalados o no se encuentran en el `PATH`. | Pulsar el botón `Sistema listo ✓` / `Atención necesaria ⚠️` en la web o ejecutar `python -m playlist_sync doctor` e instalar el programa faltante. |
| `EMPTY_OR_SHRUNK` | `La playlist apareció vacía o con muchas menos canciones. No cambié nada por seguridad.` | **No** | La fuente remota devolvió `0` elementos o menos del `50 %` (`safety_threshold = 0.50`) de las canciones que tenía registradas (`last_known_count`). | Revisar si YouTube falló temporalmente o si realmente vaciaste más de la mitad de la playlist. Tus archivos locales siguen intactos. |
| `UNKNOWN` | `Ocurrió un problema inesperado. Se guardó el detalle técnico en el registro.` *(En conflicto 409 de candado ocupado: `Ya hay una sincronización en curso. Por favor espera a que termine.`)* | **Sí** (salvo error interno fatal) | Error no clasificado o intento de lanzar dos sincronizaciones simultáneas. | Si era por descarga en curso, esperar a que termine; si persiste, revisar `playlist_sync.log`. |

---

## 9. Dónde Quedan los Archivos, Etiquetas ID3 y Base de Datos (`VERIFICADO`)

### 9.1 Estructura real de carpetas dentro de `music_root` (`VERIFICADO` en `src/playlist_sync/adapters/library.py:214-339`, `src/playlist_sync/adapters/ytdlp_source.py:212-233`, `src/playlist_sync/adapters/rss_source.py:265-282`)

Por defecto, la carpeta raíz de música es `./music_root` (dentro de la carpeta del proyecto, salvo que se cambie en `config.toml`):

```text
playlist-sync/
├── config.toml                                      # Archivo de configuración
├── playlist_sync.sqlite3                            # Base de datos SQLite local
├── playlist_sync.log                                # Registro rotativo (máx. 5 MB x 3 respaldos: .log.1, .log.2, .log.3)
├── backups/                                         # Respaldos automáticos de la BD (fuera de music_root)
│   └── playlist_sync_backup_YYYYMMDD_HHMMSS_ffffff.sqlite3
└── music_root/                                      # Carpeta que se comparte con Syncthing
    ├── Rock en Espanol/                             # 1 carpeta por fuente (nombre saneado)
    │   ├── cover.jpg                                # Portada descargada (WebP convertida a JPEG si hay ffmpeg)
    │   ├── Rock en Espanol.m3u8                     # Lista de reproducción UTF-8 con rutas relativas
    │   ├── Soda Stereo - De Musica Ligera [dQw4w9WgXcQ].mp3
    │   └── Heroes del Silencio - Entre Dos Tierras [9bZkp7q19f0].mp3
    └── Radio Ambulante/
        ├── cover.jpg
        ├── Radio Ambulante.m3u8
        └── El viaje [ep_guid_12345].mp3
```

### 9.2 Reglas de nombres de carpetas y archivos (`VERIFICADO` en `src/playlist_sync/adapters/repo.py:68-98,176-188`)
1. **Caracteres prohibidos eliminados:** Se reemplazan `<>:"/\|?*` y caracteres de control (`\x00-\x1f`) por espacios, y se recortan puntos y espacios al inicio y al final (`sanitize_filename`).
2. **Nombres reservados de Windows protegidos (`H-20`):** Si el nombre base coincide (sin importar mayúsculas) con `CON`, `PRN`, `AUX`, `NUL`, `COM1`..`COM9` o `LPT1`..`LPT9`, se le antepone un guion bajo (ej. `CON` → `_CON`, `nul.txt` → `_nul.txt`).
3. **Colisiones de nombres de carpetas:** Si agregas dos playlists que se llaman igual (incluso variando mayúsculas/minúsculas, ej. `Favoritas` y `favoritas`), la segunda carpeta se nombra automáticamente `favoritas (1)`, `favoritas (2)`, etc. (`repo.py:176-188`).
4. **Sufijo inmutable `[{external_id}].mp3`:** Cada archivo MP3 termina siempre con ` [<external_id>].mp3` (en YouTube es el ID de 11 caracteres del video; en RSS es un identificador alfanumérico limpio derivado del `<guid>` o URL del episodio). **Nunca cambia de nombre aunque cambie el orden de la playlist**, garantizando que Syncthing no vuelva a transferir el archivo por un simple reordenamiento (`PROMPT_MAESTRO.md:364-370`).

### 9.3 Cómo es el archivo `.m3u8` (`VERIFICADO` en `src/playlist_sync/adapters/library.py:292-339`)
- Se guarda como `<folder_name>/<folder_name>.m3u8` codificado en **UTF-8 sin BOM**.
- Contiene únicamente **nombres de archivo relativos** (sin `/home/...` ni `C:\...`), por lo que funciona idéntico en Linux, Windows y Android:
  ```m3u8
  #EXTM3U
  #EXTINF:-1,Soda Stereo - De Musica Ligera
  Soda Stereo - De Musica Ligera [dQw4w9WgXcQ].mp3
  ```
- **Orden de las pistas:**
  - En **playlists de música (`yt_playlist`)**: ordenadas por posición ascendente (`position` `1, 2, 3...`).
  - En **podcasts (`yt_podcast` y `rss_podcast`)**: ordenados del **más reciente al más antiguo** (`published_at` descendente).
- Solo incluye canciones con estado `downloaded`, cuyo archivo `.mp3` exista físicamente en disco y que no estén marcadas como retiradas (`removed_remote == False`).

### 9.4 Qué etiquetas ID3 se escriben en cada `.mp3` (`VERIFICADO` en `src/playlist_sync/adapters/library.py:38-47,162-205,255-272`)
Se escriben etiquetas estándar **`ID3v2.3`** (la versión más compatible con reproductores Android y de automóvil):
- **`TIT2` (Título de la canción):** Si el título del video contiene `" - "`, `" — "` o `" | "` (ej. `"Soda Stereo - De Música Ligera"`), separa automáticamente la segunda parte como título (`"De Música Ligera"`). Si no tiene separador, usa el título completo.
- **`TPE1` (Artista):** Si el título tenía separador (`"Artista - Canción"`), usa la primera parte; si no, usa el autor del canal/programa (`item.artist`, extraído de `artist`/`creator`/`uploader`/`channel` en YouTube o `itunes:author`/`author` en RSS) y, como último respaldo, el título de la fuente (`source.title`).
- **`TALB` (Álbum):** El título de la playlist o del podcast (`source.title`).
- **`TRCK` (Número de pista):** `<posición>/<total>` (ej. `3/15`). Si cambia la posición de una canción ya descargada en la playlist remota, se actualiza únicamente su etiqueta `TRCK` sin renombrar ni volver a descargar el MP3 (`library.py:276-290`).
- **`TCON` (Género):** Se escribe `"Podcast"` cuando la fuente es `yt_podcast` o `rss_podcast` (`library.py:257-259`).
- **`TDRC` (Fecha de publicación):** Fecha en formato `YYYY-MM-DD` si la fuente informa `published_at` (`library.py:260`).
- **`APIC` (Carátula frontal embebida, `type=3`):** Incrusta los bytes de `cover.jpg` con su MIME real (`image/jpeg`, `image/png` o `image/webp`; si la portada original de YouTube venía en formato WebP y `ffmpeg` está instalado, la convierte automáticamente a JPEG, `library.py:64-109`).

### 9.5 Dónde están la base de datos, los respaldos y los logs (`VERIFICADO`)
- **Base de datos SQLite:** `playlist_sync.sqlite3` en la raíz del proyecto (configurable en `config.toml` → `storage.database_path`). Contiene las tablas `schema_version`, `sources`, `items` y `settings` (`src/playlist_sync/adapters/repo.py:19-65`).
- **Respaldos automáticos de la base de datos:** Carpeta `backups/` en la raíz del proyecto. Cada vez que arranca el servidor (`serve`) y ya existe `playlist_sync.sqlite3`, crea un respaldo consistente usando la API online `sqlite3.Connection.backup()` llamado `playlist_sync_backup_YYYYMMDD_HHMMSS_ffffff.sqlite3` y conserva los **5 más recientes** (`max_backups = 5`), borrando únicamente respaldos antiguos dentro de `backups/` (`src/playlist_sync/services/backup.py:31-81`).
- **Archivo de registro (logs):** `playlist_sync.log` en la raíz del proyecto (configurable en `config.toml` → `server.log_file`). Usa rotación automática (`RotatingFileHandler`) con un tamaño máximo de **5 MB por archivo** y hasta **3 archivos históricos** (`playlist_sync.log.1`, `playlist_sync.log.2`, `playlist_sync.log.3`) en codificación UTF-8 (`src/playlist_sync/logging_config.py:10-45`).

---

## 10. Referencia Completa de `config.toml` (`VERIFICADO` en `config.toml:1-33` y `src/playlist_sync/main.py:71-93,373-388,434-440`)

| Sección y clave | Valor por defecto en `config.toml` | Qué hace exactamente | Cuándo conviene cambiarlo (ejemplo) |
|---|---|---|---|
| `[server]`<br>`host` | `"127.0.0.1"` | Dirección IP en la que escucha el servidor web FastAPI/Uvicorn. Con `"127.0.0.1"` solo responde dentro de la misma PC. | Cámbialo a `"0.0.0.0"` cuando quieras abrir la página web desde tu celular en el Wi-Fi de tu casa. |
| `[server]`<br>`port` | `8000` | Puerto TCP del servidor web. | Cámbialo a `8080` o `9000` si el puerto `8000` ya está ocupado por otro programa en tu PC. |
| `[server]`<br>`log_level` | `"INFO"` | Nivel de detalle de los mensajes guardados en `playlist_sync.log` (`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`). | Cámbialo a `"DEBUG"` si necesitas diagnosticar un problema técnico detallado. |
| `[server]`<br>`log_file` | `"playlist_sync.log"` | Ruta del archivo donde se guardan los registros rotativos del servidor. | Cámbialo si prefieres guardar los logs en otra ruta (ej. `"/var/log/playlist_sync.log"`). |
| `[storage]`<br>`music_root` | `"music_root"` | Carpeta donde se crean las subcarpetas de cada playlist/podcast con sus `.mp3`, `cover.jpg` y `.m3u8`. | Cámbialo a `"/home/usuario/Musica/PlaylistSync"` (o `"D:/Musica"` en Windows) para apuntar directo a tu carpeta compartida en Syncthing o a un segundo disco duro. |
| `[storage]`<br>`database_path` | `"playlist_sync.sqlite3"` | Ruta del archivo de base de datos SQLite local. | Rara vez se cambia; útil si quieres guardar la base de datos en una ruta distinta del código. (Nunca la pongas dentro de `music_root`). |
| `[storage]`<br>`min_disk_free_mb` | `1024` | Megabytes mínimos de espacio libre que debe tener el disco antes de permitir descargas. Si hay menos, aborta con `DISK_FULL`. | Si tu disco está casi lleno pero aún quieres descargar unas pocas canciones, puedes bajarlo a `512`; si quieres más margen en una PC dedicada, súbelo a `5120` (5 GB). |
| `[sync]`<br>`interval_hours` | `6` | Cada cuántas horas el programador automático (`PeriodicSyncScheduler`) revisa y descarga novedades de todas las fuentes mientras el servidor está encendido. Si se pone en `0` (o negativo), se desactiva. | Ponlo en `12` o `24` si quieres que revise solo una o dos veces al día, o en `0` si prefieres actualizar únicamente cuando tú pulses el botón `Actualizar todo`. |
| `[sync]`<br>`max_retries` | `3` | Número máximo de intentos automáticos para canciones que fallaron por causas temporales (`RATE_LIMITED`, `NETWORK`, `ITEM_UNAVAILABLE`). | Súbelo a `5` si tu conexión a internet en casa es muy inestable. |
| `[sync]`<br>`safety_threshold` | `0.50` | Umbral de protección (`50 %`): si una playlist que tenía `N` canciones conocidas aparece de pronto en YouTube con menos de `N * 0.50` canciones (o `0`), la sincronización se aborta con `EMPTY_OR_SHRUNK` sin tocar el `.m3u8`. | Si tú mismo borraste a propósito más de la mitad de las canciones de una playlist en YouTube y quieres que Playlist Sync acepte el nuevo tamaño, bájalo temporalmente a `0.10`, sincroniza esa lista y vuélvelo a poner en `0.50`. |
| `[sync]`<br>`concurrency` | `1` | Indicador documental de descargas secuenciales (el motor descarga siempre de 1 en 1 para cuidar hardware modesto). | Déjalo siempre en `1`. |
| `[sync]`<br>`sleep_interval` | `2.0` | Segundos de pausa que espera `yt-dlp` antes de descargar cada archivo de audio de YouTube (`H-17`). | Súbelo a `5.0` si descargas listas muy grandes y quieres reducir aún más el riesgo de bloqueo temporal (`RATE_LIMITED`) de YouTube. |
| `[sync]`<br>`sleep_interval_requests` | `1.0` | Segundos de pausa entre solicitudes HTTP de metadatos hacia YouTube (`H-17`). | Súbelo a `2.0` si YouTube limita las consultas en tu conexión residencial. |
| `[sync]`<br>`rate_limit_bytes` | `0` | Límite máximo de velocidad de descarga en bytes por segundo (`0` = sin límite). | Si no quieres que las descargas consuman todo el ancho de banda de tu casa, pon por ejemplo `1048576` (`1 MB/s`). |

---

## 11. Entrega al Celular con Syncthing (`VERIFICADO` en `docs/syncthing.md` y fuentes web actuales 2025/2026)

### 11.1 ¿Cuál es la aplicación de Syncthing para Android mantenida hoy? (`VERIFICADO` vía `docs/syncthing.md:14-21` y búsqueda web actualizada)
- La app oficial original de Syncthing para Android fue discontinuada y archivada en Google Play a finales de 2024.
- Durante años, la comunidad usó **Syncthing-Fork** mantenida por **Catfriend1**. A finales de 2025, Catfriend1 se retiró y transfirió el repositorio a la organización/mantenedor comunitario **`researchxxl/syncthing-android`**, que es quien mantiene activamente **Syncthing-Fork** hoy en 2026 (con soporte para Syncthing v2, tarjetas SD y mejoras de batería):
  - **GitHub Releases (mantenido actualmente):** `https://github.com/researchxxl/syncthing-android/releases`
  - **F-Droid:** `https://f-droid.org/packages/com.github.catfriend1.syncthingandroid/` (paquete `com.github.catfriend1.syncthingandroid`)
  - **Google Play Store:** buscar *Syncthing-Fork*.

### 11.2 Pasos exactos de configuración PC ↔ Celular (`VERIFICADO` en `docs/syncthing.md:23-55`)
1. **Instalar y activar Syncthing en la PC:**
   - **En Linux Mint / Ubuntu:**
     ```bash
     sudo apt install syncthing
     systemctl --user enable --now syncthing.service
     ```
   - **En Windows 11:**
     ```powershell
     winget install Syncthing.Syncthing
     ```
   - Abre el panel de Syncthing en el navegador de la PC: `http://127.0.0.1:8384`.
2. **Instalar Syncthing-Fork en el celular Android y excluir del ahorro de batería:**
   - Instala **Syncthing-Fork** y concédele permiso de acceso al almacenamiento para la carpeta de música (`/storage/emulated/0/Music`).
   - **Paso crítico de batería:** En los ajustes de Android ve a **Ajustes → Aplicaciones → Syncthing-Fork → Batería** y selecciona **"Sin restricciones"** (o desactiva la optimización de batería) para que Android no cierre Syncthing en segundo plano.
3. **Emparejar ambos dispositivos:**
   - En Syncthing de la PC (`http://127.0.0.1:8384`), pulsa **Agregar dispositivo** y escanea el código QR que muestra Syncthing-Fork en el celular. Acepta en ambos lados.
4. **Compartir la carpeta `music_root` con la Regla de Oro (Enviar solamente / Recibir solamente):**
   - **En la PC:** Pulsa **Agregar carpeta**:
     - **Etiqueta de la carpeta:** `Musica`
     - **Ruta de la carpeta:** La ruta absoluta de tu carpeta `music_root` (ej. `/home/gabriel/Proyectos/playlist-sync/music_root`).
     - En la pestaña **Compartir**, marca tu celular.
     - En la pestaña **Avanzado → Tipo de carpeta**, elige **"Solo enviar" (*Send Only*)**.
   - **En el celular:** Toca la notificación *"Dispositivo PC desea compartir la carpeta Musica"*:
     - Elige como destino una carpeta dentro de la música de tu teléfono (ej. `/storage/emulated/0/Music/PlaylistSync`).
     - En **Tipo de carpeta**, elige **"Solo recibir" (*Receive Only*)** y guarda.

---

## 12. Cómo Hacer que el Reproductor del Celular Detecte las Playlists (`VERIFICADO` en `docs/syncthing.md:58-63` y `src/playlist_sync/adapters/library.py:162-205,292-339`; prueba en teléfono físico: `NO VERIFICABLE AQUÍ`)

Playlist Sync utiliza una **doble estrategia** para que cualquier reproductor móvil organice tus listas sin esfuerzo:
1. **Por archivos de lista `.m3u8`:** Dentro de cada subcarpeta (`music_root/<Nombre de Lista>/`) hay un archivo `<Nombre de Lista>.m3u8` con rutas relativas (solo el nombre de cada `.mp3`). Reproductores recomendados como **Musicolet**, **AIMP**, **Poweramp**, **Opal** o **VLC** detectan automáticamente los archivos `.m3u8` al escanear la carpeta `Music/PlaylistSync` y muestran la lista con el orden exacto.
2. **Por etiquetas de Álbum (`TALB`) y Pista (`TRCK`):** Incluso si un reproductor sencillo no lee archivos `.m3u8`, todas las canciones de una misma playlist tienen el nombre de la playlist grabado en la etiqueta ID3 **Álbum (`TALB`)**, la portada incrustada en cada `.mp3` (`APIC`) y el número de orden en **Pista (`TRCK`)**. Basta con abrir la pestaña **"Álbumes"** o **"Carpetas"** del reproductor para ver cada playlist agrupada con su carátula.

### Qué hacer si el reproductor del celular no muestra las canciones nuevas o las listas `.m3u8` (`NO VERIFICADO` en app móvil)
1. **Forzar re-escaneo de biblioteca en el reproductor:** En Musicolet / Poweramp / AIMP, pulsa **"Escanear carpetas"** o **"Actualizar biblioteca"** y asegúrate de que la carpeta `Music/PlaylistSync` esté marcada entre las carpetas vigiladas.
2. **Verificar que no exista un archivo `.nomedia`:** Comprueba que en `Music/PlaylistSync` (ni en la carpeta superior) haya un archivo oculto llamado `.nomedia`, ya que ese archivo le ordena a Android ocultar toda la música de esa carpeta.
3. **Si modificaste algo por error en el teléfono:** Abre Syncthing-Fork en el celular y, si aparece el botón rojo **"Revertir cambios locales" (*Revert Local Changes*)**, púlsalo para que el teléfono vuelva a quedar idéntico a la carpeta `music_root` de la PC (`docs/syncthing.md:79-80`).

---

## 13. Mantenimiento del Sistema (`VERIFICADO`)

### 13.1 Cómo se actualiza `yt-dlp` y qué hacer cuando YouTube cambia algo y deja de descargar (`VERIFICADO` en `src/playlist_sync/main.py:31-68,444` y `start.sh:11`)
- **Actualización automática en cada arranque (`RF-16`):** Cada vez que inicias Playlist Sync (ya sea con `./start.sh`, `start.bat`, el servicio `systemd` o `python -m playlist_sync serve`), el sistema ejecuta automáticamente:
  ```bash
  .venv/bin/python -m pip install --upgrade --no-input "yt-dlp[default]"
  ```
  Si tiene éxito, escribe en `playlist_sync.log`:
  `Auto-actualización de yt-dlp[default] completada exitosamente.`
  Si en ese momento no hay internet, escribe un `WARNING` en el log y **arranca normalmente** con la versión ya instalada.
- **Qué hacer si un día YouTube cambia su página y fallan las descargas con el servidor ya encendido:**
  Como el servidor en Linux Mint puede llevar semanas encendido sin reiniciarse, basta con actualizar `yt-dlp[default]` manualmente o reiniciar el servicio (lo cual dispara la auto-actualización):
  ```bash
  # En Linux Mint (con servicio systemd):
  systemctl --user restart playlist-sync.service

  # O manualmente desde la carpeta del proyecto en Linux Mint:
  .venv/bin/pip install --upgrade "yt-dlp[default]"

  # En Windows 11:
  .\.venv\Scripts\pip.exe install --upgrade "yt-dlp[default]"
  ```

### 13.2 Respaldos de la base de datos y cómo restaurarlos (`VERIFICADO` en `src/playlist_sync/main.py:246-265,334-345` y `src/playlist_sync/services/backup.py:31-111`)
- **Respaldo automático:** Se crea solo cada vez que inicia `serve`, guardando hasta 5 archivos en `backups/playlist_sync_backup_YYYYMMDD_HHMMSS_ffffff.sqlite3`.
- **Crear un respaldo manual en cualquier momento:**
  ```bash
  .venv/bin/python -m playlist_sync backup
  # Salida literal:
  # [OK] Respaldo de base de datos generado en: /ruta/.../backups/playlist_sync_backup_YYYYMMDD_HHMMSS_ffffff.sqlite3
  ```
  *(Opcionalmente puedes indicar otra carpeta con `--dir otra_carpeta`, siempre que no se llame `music_root`).*
- **Restaurar un respaldo (`restore-backup`):**
  1. Detén primero el servidor para que no esté escribiendo en la base de datos (`systemctl --user stop playlist-sync.service` o `Ctrl + C`).
  2. Lista tus respaldos disponibles en `backups/`:
     ```bash
     ls -lh backups/
     ```
  3. Ejecuta el comando de restauración indicando el archivo `.sqlite3`:
     ```bash
     .venv/bin/python -m playlist_sync restore-backup backups/playlist_sync_backup_20261102_200000_000000.sqlite3
     ```
     El comando comprueba que el respaldo exista, que no pese `0 bytes` y que pase `PRAGMA integrity_check;` de SQLite antes de restaurarlo (`backup.py:89-105`), e imprime:
     ```text
     [OK] Base de datos restaurada exitosamente en: /ruta/.../playlist_sync.sqlite3
     ```
  4. Vuelve a iniciar el servidor (`systemctl --user start playlist-sync.service` o `./start.sh`).

### 13.3 Comando `doctor` y cómo interpretar su salida (`VERIFICADO` ejecutando `.venv/bin/python -m playlist_sync doctor` y leyendo `src/playlist_sync/doctor.py:88-307`)

Ejecuta:
```bash
.venv/bin/python -m playlist_sync doctor
```
El comando lee `config.toml` (para revisar la carpeta `music_root` y el `min_disk_free_mb` reales configurados) y evalúa 6 puntos:

| Nombre del chequeo | Categoría | Qué significa `[OK]` | Qué muestra si falla (`[ERROR]` o `[AVISO]`) y solución literal |
|---|---|---|---|
| `Python` | `(REQUERIDO)` | `Instalado (versión 3.12.x)` | `[ERROR]` `Versión no compatible (X.Y.Z). Se requiere Python 3.12 o superior.`<br>`-> Solucion: Actualiza Python a la versión 3.12 o posterior (ej. en Ubuntu: apt install python3.12).` |
| `ffmpeg` | `(REQUERIDO)` | `Instalado (ffmpeg version ...)` | `[ERROR]` `No se encontró ffmpeg en el sistema.`<br>`-> Solucion: En Linux: ejecuta 'sudo apt install ffmpeg'. En Windows: ejecuta 'winget install Gyan.FFmpeg' y reinicia la terminal.` |
| `Runtime JS (Deno/Node)` | `(OPCIONAL)` | `Instalado (Deno: ...)` o `Instalado (Node.js: ...)` | `[AVISO]` `No se encontró Deno ni Node.js.`<br>`-> Solucion: Recomendado para resolver retos de YouTube en yt-dlp. En Linux instala Deno con: 'curl -fsSL https://deno.land/install.sh \| sh'. En Windows con: 'winget install DenoLand.Deno'.` |
| `yt-dlp` | `(REQUERIDO)` | `Instalado (versión 2026.x.x)` | `[ERROR]` `El módulo 'yt-dlp' no está instalado en el entorno de Python.`<br>`-> Solucion: Instálalo en tu entorno virtual con: 'pip install yt-dlp'.` |
| `Espacio en disco` | `(REQUERIDO)` | `Suficiente: X.X GB disponibles (mínimo requerido: 1024 MB)` | `[ERROR]` `Espacio insuficiente: solo hay X MB libres (se requieren al menos 1024 MB).`<br>`-> Solucion: Libera espacio en el disco antes de iniciar descargas.` |
| `Permisos de escritura` | `(REQUERIDO)` | `Correctos en '<music_root>'` | `[ERROR]` `No se tienen permisos de escritura en '<music_root>'.`<br>`-> Solucion: En Linux: revisa el propietario de la carpeta con 'sudo chown -R $USER <ruta>'. En Windows: comprueba la seguridad de la carpeta en sus Propiedades.` |

### 13.4 Cómo ejecutar las pruebas automáticas (`VERIFICADO` en `README.md:177-190` y ejecutado en este equipo)
```bash
# Suite rápida y completa sin red (150 pruebas, ~70 segundos):
.venv/bin/pytest -m "not network"

# Suite con reporte de cobertura del núcleo (core/ >= 80%, actual: 95.37%):
.venv/bin/pytest -m "not network" --cov=src/playlist_sync/core --cov-report=term-missing

# Pruebas E2E de interfaz y ciclo de vida completo:
.venv/bin/pytest tests/e2e/test_ui_playwright.py -v

# Pruebas reales contra YouTube en vivo (requiere internet, descarga 1 canción real):
.venv/bin/pytest -m network -v -s

# Verificación de estilo, formato y tipos:
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src/playlist_sync
```

---

## 14. Mover el Servidor a Otra PC (`export`, `import` y `reconcile`) (`VERIFICADO` en `src/playlist_sync/services/migration.py:18-105` y `src/playlist_sync/services/sync.py:282-395`)

Nunca copies el archivo binario `playlist_sync.sqlite3` entre computadoras distintas si están sincronizadas con Syncthing o tienen rutas distintas. El procedimiento oficial utiliza `sources.json` y la reconciliación con disco (`RF-19` y `RF-20`):

### Paso 1: En la PC antigua (exportar tus listas)
```bash
.venv/bin/python -m playlist_sync export
# Salida literal:
# [OK] Fuentes exportadas exitosamente a: sources.json
```
Esto genera un archivo de texto `sources.json` con la versión (`"version": 1`), fecha de exportación y la lista de tus fuentes (`kind`, `url`, `title`, `cover_url`, `folder_name`).

### Paso 2: En la PC nueva (copiar archivos, importar y reconciliar sin volver a descargar)
1. Instala Playlist Sync en la PC nueva (`./install.sh` o `.\install.ps1`).
2. Si ya tienes tus carpetas de música con los archivos `.mp3` (por ejemplo, copiadas en un disco USB o sincronizadas por Syncthing), colócalas dentro de la carpeta `music_root` de la PC nueva.
3. Copia el archivo `sources.json` a la carpeta de Playlist Sync en la PC nueva y ejecuta:
   ```bash
   .venv/bin/python -m playlist_sync import sources.json
   # Salida literal:
   # [OK] Importacion exitosa: X importadas, 0 omitidas.
   ```
   *(Es idempotente: si ejecutas `import` dos veces, las fuentes que ya existen por URL se cuentan como `omitidas` sin duplicarse).*
4. **Reconciliar con los archivos ya presentes en el disco (`RF-20`):**
   Para que la base de datos nueva reconozca todos los `.mp3` que ya están en `music_root` sin descargarlos otra vez de internet, ejecuta:
   ```bash
   .venv/bin/python -m playlist_sync reconcile
   # Salida literal:
   # [OK] Reconciliacion con disco completada: N elementos marcados como descargados.
   ```
   *(También puedes hacerlo desde la página web pulsando el botón superior **`Verificar archivos`**).*

### ¿Qué se conserva y qué se pierde al migrar con `sources.json`? (`VERIFICADO` en `src/playlist_sync/services/migration.py:24-38` y `src/playlist_sync/services/sync.py:285-395`)
- **Se conserva al 100 %:** Todas tus suscripciones (URLs de playlists y podcasts), títulos, nombres de carpeta (`folder_name`), todos tus archivos `.mp3` existentes (reconocidos por el sufijo `[external_id].mp3`), sus portadas `cover.jpg` y las listas `.m3u8`.
- **No viaja en `sources.json` (se regenera solo):** El historial de fechas exactas de sincronización anteriores (`last_sync_at`) y el conteo histórico de errores previos (`attempts` / `error_message` de canciones que nunca llegaron a descargarse).

---

## 15. Sincronización Automática Programada (`RF-17`) (`VERIFICADO` en `src/playlist_sync/services/scheduler.py:14-84` y `config.toml:18-19`)

- **Cómo funciona:** Cuando el servidor web está corriendo (`serve`), la clase `PeriodicSyncScheduler` inicia una tarea en segundo plano que espera `interval_hours * 3600` segundos y luego dispara automáticamente el equivalente a **"Actualizar todo"** (`job_executor.trigger_sync_all()`).
- **Qué pasa si ya estabas descargando algo a esa hora:** Si el candado `job_executor.is_running` está ocupado, el programador registra en el log `Skipping scheduled sync: a synchronization is already in progress` y espera al siguiente ciclo sin interrumpir tu descarga (`scheduler.py:74-78`).
- **Intervalo por defecto:** Cada **`6` horas** (`interval_hours = 6` en `config.toml`).
- **Cómo cambiar el intervalo o desactivarlo:**
  1. Abre `config.toml` con un editor de texto.
  2. En la sección `[sync]`, modifica `interval_hours`:
     - Para revisar cada 12 horas: `interval_hours = 12`
     - Para **desactivar por completo** la sincronización automática: `interval_hours = 0`
  3. Reinicia el servidor (`systemctl --user restart playlist-sync.service` en Linux Mint, o cierra y vuelve a abrir `start.bat` en Windows).

---

## 16. Guía de Solución de Problemas (16 Situaciones Reales Verificadas)

### Problema 1: La página no abre desde el celular (`http://<IP>:8000` da error de conexión)
- **Síntoma:** En la PC abre bien `http://localhost:8000`, pero en el navegador del teléfono dice *"No se puede acceder a este sitio"*.
- **Causa:** Por defecto `config.toml` tiene `host = "127.0.0.1"` (solo escucha dentro de la PC) o el firewall bloquea el puerto `8000`. (`VERIFICADO` en `config.toml:4`).
- **Solución:**
  1. En `config.toml`, cambia `host = "127.0.0.1"` por `host = "0.0.0.0"`.
  2. Reinicia el servicio: `systemctl --user restart playlist-sync.service`.
  3. Si usas UFW en Linux Mint, abre el puerto: `sudo ufw allow 8000/tcp`.
  4. Verifica la IP de la PC con `hostname -I` y entra desde el celular a `http://<IP>:8000`.

### Problema 2: Al guardar una playlist aparece *"Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar."*
- **Síntoma:** No se crea la tarjeta y aparece el recuadro rojo con ese mensaje exacto (`ErrorCode.PRIVATE_SOURCE`).
- **Causa:** La lista en YouTube es privada (por ejemplo, la lista automática *"Videos que me gustan"* / `LL` siempre es privada, o una lista nueva creada como Privada). (`VERIFICADO` en `src/playlist_sync/core/errors.py:24`).
- **Solución:** Abre la playlist en la app o web de YouTube → toca el icono de lápiz (Editar) → cambia **Privacidad** de *Privada* a **No listada** (o **Pública**) → guarda y vuelve a pegar el link en Playlist Sync.

### Problema 3: Una tarjeta muestra *"Hubo un problema"* y *"La playlist apareció vacía o con muchas menos canciones. No cambié nada por seguridad."*
- **Síntoma:** La sincronización se detiene con `ErrorCode.EMPTY_OR_SHRUNK` y no se modifica el archivo `.m3u8`.
- **Causa:** Se activó la protección del umbral del 50 % (`RF-12` / `safety_threshold = 0.50` en `config.toml:24`) porque YouTube devolvió menos de la mitad de las canciones que tenía la lista en la última sincronización exitosa. (`VERIFICADO` en `src/playlist_sync/core/sync_rules.py:28-50`).
- **Solución:**
  - Si tú NO borraste canciones en YouTube, fue un fallo momentáneo de red/YouTube: simplemente espera unos minutos y pulsa **`Actualizar`**.
  - Si tú SÍ eliminaste más de la mitad de las canciones a propósito en YouTube, edita `config.toml`, cambia temporalmente `safety_threshold = 0.0`, reinicia el servidor, pulsa **`Actualizar`** en esa lista y vuelve a dejar `safety_threshold = 0.50`.

### Problema 4: Aparece el mensaje *"YouTube pidió esperar un poco. Intenta de nuevo en unos minutos."*
- **Síntoma:** Algunas canciones quedan con error `RATE_LIMITED`.
- **Causa:** YouTube detectó muchas solicitudes seguidas desde tu dirección IP residencial (HTTP 429 / límite de tasa). (`VERIFICADO` en `src/playlist_sync/core/errors.py:30,160-175`).
- **Solución:**
  1. Espera de 10 a 15 minutos antes de pulsar **`Actualizar`** o **`Reintentar`**.
  2. Si tienes listas muy grandes, aumenta las pausas en `config.toml`:
     ```toml
     sleep_interval = 5.0
     sleep_interval_requests = 2.0
     ```
     y reinicia el servidor.

### Problema 5: Aparece *"No hay espacio en el disco."* (`DISK_FULL`)
- **Síntoma:** No inicia ninguna descarga y muestra `No hay espacio en el disco.`.
- **Causa:** El disco donde está `music_root` tiene menos de `1024 MB` libres (`min_disk_free_mb` en `config.toml:15`). (`VERIFICADO` en `src/playlist_sync/services/sync.py:21-35`).
- **Solución:** Comprueba el espacio libre con `.venv/bin/python -m playlist_sync doctor` o `df -h`, libera espacio en tu disco duro (o reduce `min_disk_free_mb = 512` en `config.toml`).

### Problema 6: Aparece *"Ya hay una descarga en curso. Espera a que termine."*
- **Síntoma:** Al pulsar **`Actualizar`**, **`Actualizar todo`** o **`Reintentar`**, sale un aviso flotante y no inicia otra tarea (`409 Conflict`).
- **Causa:** El candado exclusivo (`JobExecutor._lock`, `RF-11`) solo permite una sincronización activa a la vez para no saturar la PC ni mezclar descargas. (`VERIFICADO` en `src/playlist_sync/services/jobs.py:121-185`).
- **Solución:** Observa el banner azul superior y espera a que termine la descarga actual antes de iniciar otra.

### Problema 7: Una canción dice *"Este video tiene restricción de edad y no se puede descargar."* o *"Este video no está disponible en tu país."*
- **Síntoma:** La canción queda marcada en rojo dentro de `Ver canciones` y aunque sincronices la lista no se descarga (`AGE_RESTRICTED` o `GEO_BLOCKED`).
- **Causa:** Son errores permanentes (`NON_RETRYABLE_ERROR_CODES` en `src/playlist_sync/core/sync_rules.py:17-25`) porque el video exige iniciar sesión con cuenta +18 o está bloqueado en tu país.
- **Solución:** En YouTube, reemplaza ese video de tu playlist por otra versión de la misma canción subida por otro canal (por ejemplo, el audio oficial o letra) y pulsa **`Actualizar`** en Playlist Sync.

### Problema 8: YouTube cambió su sistema y de pronto fallan todas las descargas de YouTube
- **Síntoma:** Los podcasts RSS descargan bien, pero cualquier canción de YouTube falla con error `UNKNOWN` o `ITEM_UNAVAILABLE`.
- **Causa:** YouTube actualiza periódicamente su reproductor web y requiere la última versión de `yt-dlp` y `yt-dlp-ejs`. (`VERIFICADO` en `src/playlist_sync/main.py:31-68`).
- **Solución:** Ejecuta en la terminal:
  ```bash
  .venv/bin/pip install --upgrade "yt-dlp[default]"
  systemctl --user restart playlist-sync.service
  ```

### Problema 9: El servicio `systemd` en Linux Mint o `doctor` dice que no encuentra Deno
- **Síntoma:** `doctor` muestra `[AVISO] Runtime JS (Deno/Node) (OPCIONAL): No se encontró Deno ni Node.js.`.
- **Causa:** Deno no se instaló o el archivo de servicio no se regeneró con `./systemd/install-service.sh`. (`VERIFICADO` en `src/playlist_sync/doctor.py:182-192` y `systemd/playlist-sync.service:17`).
- **Solución:**
  ```bash
  curl -fsSL https://deno.land/install.sh | sh
  ./systemd/install-service.sh
  ```

### Problema 10: El servicio en Linux Mint se apaga cuando cierras sesión o reinicias la PC sin iniciar sesión gráfica
- **Síntoma:** Al encender la PC sin entrar al escritorio de Linux Mint, el celular no conecta a `http://<IP>:8000`.
- **Causa:** No se activó `linger` para tu usuario en `loginctl`. (`VERIFICADO` en `systemd/install-service.sh:25-26`).
- **Solución:** Ejecuta en la terminal de Linux Mint:
  ```bash
  sudo loginctl enable-linger "$USER"
  systemctl --user enable --now playlist-sync.service
  ```

### Problema 11: Importé mis listas (`sources.json`) en una PC nueva donde ya estaban los MP3, pero aparecen como *"Pendientes"*
- **Síntoma:** Las tarjetas dicen `0 de N listas` y quieren volver a descargar canciones cuyos archivos `.mp3` ya están dentro de `music_root`.
- **Causa:** La base de datos nueva aún no ha escaneado el disco (`RF-20`). (`VERIFICADO` en `src/playlist_sync/services/sync.py:285-395`).
- **Solución:** Pulsa el botón **`Verificar archivos`** arriba a la derecha en la página web, o ejecuta en terminal:
  ```bash
  .venv/bin/python -m playlist_sync reconcile
  ```

### Problema 12: Borré por accidente un archivo `.mp3` de la carpeta `music_root` y quiero que lo vuelva a descargar
- **Síntoma:** En la base de datos figuraba como `downloaded`, pero el archivo `.mp3` ya no existe en la carpeta.
- **Causa:** El archivo fue eliminado manualmente fuera de Playlist Sync.
- **Solución:** Simplemente pulsa **`Actualizar`** en esa tarjeta (o ejecuta `.venv/bin/python -m playlist_sync reconcile` y luego `sync`). `sync_source_service` (`src/playlist_sync/services/sync.py:155-169`) detecta automáticamente que el archivo `.mp3` ya no existe en disco, lo regresa a estado `pending` y lo vuelve a descargar.

### Problema 13: En Windows 11, al ejecutar `.\install.ps1` dice que la ejecución de scripts está deshabilitada
- **Síntoma:** PowerShell bloquea `.\install.ps1` con `PSSecurityException` (`UnauthorizedAccess`).
- **Causa:** Política de ejecución por defecto de Windows PowerShell. (`VERIFICADO` en `README.md:71-73`).
- **Solución:** Ejecútalo pasando `-ExecutionPolicy Bypass`:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```

### Problema 14: En Windows 11, `install.ps1` acaba de instalar `ffmpeg` o `deno`, pero `doctor` dice que no los encuentra
- **Síntoma:** En la misma ventana de PowerShell donde `winget` instaló `ffmpeg`, no aparece aún en la variable `PATH`.
- **Causa:** Windows no recarga las variables de entorno `PATH` en una ventana de terminal ya abierta (`install.ps1:30`). Nota: `doctor.py:110-120,152-160` ya busca automáticamente en `%LOCALAPPDATA%\Microsoft\WinGet\Packages\...`, pero para que toda tu terminal lo vea conviene reiniciarla.
- **Solución:** Cierra la ventana de PowerShell, abre una nueva y ejecuta `.\start.bat`.

### Problema 15: La base de datos `playlist_sync.sqlite3` se dañó por un apagón brusco de luz
- **Síntoma:** El servidor no arranca o muestra errores de SQLite al listar fuentes.
- **Causa:** Corte eléctrico mientras el disco escribía.
- **Solución:** Restaura el último respaldo automático de la carpeta `backups/` (`VERIFICADO` en `src/playlist_sync/services/backup.py:84-111`):
  ```bash
  systemctl --user stop playlist-sync.service
  ls -lt backups/
  .venv/bin/python -m playlist_sync restore-backup backups/<nombre_del_respaldo_mas_reciente>.sqlite3
  systemctl --user start playlist-sync.service
  ```

### Problema 16: La píldora superior derecha dice *"Servidor inaccesible"* o *"Sin conexión"*
- **Síntoma:** La página web ya estaba abierta en el navegador, pero ahora el indicador superior muestra `Servidor inaccesible` y al pulsar un botón sale `No se pudo conectar con el servidor local.` (`app.js:75,613`).
- **Causa:** El proceso de Playlist Sync en la PC se detuvo o la PC se apagó / desconectó del Wi-Fi.
- **Solución:** Verifica en la PC que el servicio esté corriendo (`systemctl --user status playlist-sync.service` en Linux Mint o que la ventana de `start.bat` siga abierta en Windows).

---

## 17. Preguntas Frecuentes de un Usuario No Técnico (`VERIFICADO`)

1. **¿Qué pasa si borro una canción de mi playlist en YouTube? ¿Se me borra del celular?**
   **No.** Playlist Sync tiene la regla inquebrantable de **nunca borrar tus archivos MP3** (`RF-12`). El archivo `.mp3` se queda guardado en tu carpeta para siempre; lo único que hace el programa es quitar esa canción de la lista de reproducción `.m3u8` para que la playlist refleje tu selección actual (`VERIFICADO` en `src/playlist_sync/services/sync.py:187-189`).
2. **¿Y si después me arrepiento y vuelvo a meter esa misma canción a la playlist de YouTube?**
   En la siguiente actualización, Playlist Sync detecta que el archivo `.mp3` ya lo tenías descargado (`H-13`), no gasta internet en descargarlo de nuevo y simplemente lo vuelve a incluir en el archivo `.m3u8` (`VERIFICADO` en `src/playlist_sync/core/sync_rules.py:92-97`).
3. **¿Gasta datos o internet volver a pulsar "Actualizar" en una lista que ya descargué?**
   Casi nada: solo consulta la lista de títulos para ver si agregaste canciones nuevas. Las canciones que ya están descargadas (`downloaded`) se saltan por completo (`skipped`) (`VERIFICADO` en `src/playlist_sync/core/sync_rules.py:67-82`).
4. **¿Necesito tener mi cuenta de YouTube abierta en la computadora del servidor?**
   **No.** De hecho, el programa no usa cuentas ni contraseñas para proteger tu privacidad y evitar que YouTube bloquee tu cuenta personal. Solo necesitas que tus playlists estén en modo **Público** o **No listado** (`VERIFICADO` en `PROMPT_MAESTRO.md:203`).
5. **¿Qué diferencia hay entre una playlist "Pública" y una "No listada" en YouTube?**
   Ambas funcionan perfecto con Playlist Sync. La ventaja de **No listada** (*Unlisted*) es que no aparece en los buscadores de YouTube ni en tu perfil público: solo quien tenga el enlace (como tu servidor Playlist Sync) puede verla.
6. **¿Puedo instalar la página web como si fuera una aplicación en la pantalla de inicio de mi celular?**
   **Sí (`RF-18`).** Incluye manifiesto PWA (`manifest.webmanifest`) e iconos. En Chrome o Firefox del celular, abre el menú de tres puntos y toca **"Agregar a la pantalla principal"** o **"Instalar aplicación"** (`VERIFICADO` en `src/playlist_sync/web/manifest.webmanifest` y `README.md:104`).
7. **¿Por qué los podcasts aparecen con el episodio más nuevo arriba y las playlists de música aparecen en el orden de YouTube?**
   Porque así es como se escuchan naturalmente: en una playlist musical quieres el orden de pistas (`1, 2, 3...`), mientras que en un podcast quieres ver primero el capítulo más reciente (`VERIFICADO` en `src/playlist_sync/adapters/library.py:319-327`).
8. **¿Tengo que apretar "Actualizar todo" todos los días?**
   No es obligatorio. Mientras la PC esté encendida, Playlist Sync revisa automáticamente todas tus listas cada **6 horas** (`interval_hours = 6`). El botón **`Actualizar todo`** está ahí para cuando acabas de agregar una canción en YouTube y la quieres en tu celular en ese mismo instante (`VERIFICADO` en `config.toml:19`).

---

## 18. Cómo Desinstalar o Limpiar Todo (`VERIFICADO` a partir de las rutas de `install-service.sh`, `install.sh` y `config.toml`)

### Paso 1: Detener y eliminar el servicio automático (en Linux Mint)
```bash
systemctl --user stop playlist-sync.service
systemctl --user disable playlist-sync.service
rm -f ~/.config/systemd/user/playlist-sync.service
systemctl --user daemon-reload
```
*(En Windows 11: borra el acceso directo a `start.bat` de la carpeta `shell:startup`).*

### Paso 2: Conservar tu música y borrar solo el programa
1. Si tu carpeta `music_root` está dentro de `playlist-sync/music_root`, muévela primero a un lugar seguro (ej. `mv music_root ~/Musica_Respaldada`).
2. Borra la carpeta del proyecto (que incluye el entorno virtual `.venv`, la base de datos `playlist_sync.sqlite3`, `backups/` y `playlist_sync.log`):
   ```bash
   cd ..
   rm -rf playlist-sync
   ```
3. *(Opcional)* Si también deseas desinstalar Deno instalado por `install.sh`:
   ```bash
   rm -rf ~/.deno
   ```

---

## 19. Estado Real del Proyecto al Cierre de la Auditoría (`5c72717`) (`VERIFICADO`)

### 19.1 Qué funciona y está 100 % verificado en este equipo (`VERIFICADO`)
- **20 de 20 hallazgos de auditoría (`H-01` a `H-20`) + `RF-20` resueltos con pruebas automáticas:**
  - **150 pruebas unitarias, de integración y E2E** sin red pasan en `69.58s` con **95.37 % de cobertura** en `src/playlist_sync/core/` (`pytest -m "not network" --cov=src/playlist_sync/core`).
  - **4 pruebas en red real contra YouTube** (`pytest -m network -v -s`) pasan en `94.08s`, descargando audio real de YouTube, incrustando carátula y etiquetas `ID3v2.3`, generando `.m3u8` relativo y comprobando que la segunda corrida no descarga nada repetido.
  - **0 errores** en `ruff check .`, `ruff format --check .` y `mypy src/playlist_sync`.
- **Seguridad verificada:** Protección anti-SSRF con validación de DNS e inspección de redirecciones HTTP (`url_security.py`), parseo XML blindado con `defusedxml`, sin `CORSMiddleware` permisivo, sin `shell=True` y sin exponer `technical_detail` en respuestas HTTP.
- **Protección de datos verificada:** Ningún módulo borra archivos `.mp3` ni `.m3u8` (comprobado por prueba AST en `test_library.py`), umbral flotante exacto del 50 % (`RF-12`), rotación segura de 5 respaldos SQLite íntegros y restauración verificada con `PRAGMA integrity_check`.

### 19.2 Qué quedó pendiente de comprobación física externa y limitaciones que el usuario debe conocer
- **Comprobación física con el teléfono Android y Syncthing-Fork (`NO VERIFICABLE AQUÍ`):** La generación de `.mp3`, `cover.jpg`, etiquetas `ID3v2.3` y `.m3u8` está verificada en disco, pero el emparejamiento físico con el teléfono del usuario y la apertura en su app reproductora móvil deben realizarse en su red doméstica siguiendo `docs/manual-checks.md` (sección 9) y `docs/syncthing.md`.
- **Ejecución nativa en una máquina física con Windows 11 (`NO VERIFICABLE AQUÍ`):** Los scripts `install.ps1` y `start.bat` y los nombres reservados de Windows (`CON`, `NUL`, etc.) están verificados por pruebas unitarias en Linux Mint, pero no se ejecutaron sobre un sistema operativo Windows 11 en esta sesión.
- **Limitación inherente a YouTube:** Si YouTube impone un bloqueo temporal de IP o cambia sus scripts de firma, el usuario debe esperar unos minutos o reiniciar el servicio para que `auto_update_ytdlp()` actualice `yt-dlp[default]`.

---

## 20. Glosario Simple para el Manual de Usuario (`VERIFICADO`)

| Término | Explicación sencilla ("a prueba de mamá") |
|---|---|
| **Fuente (*Source*)** | Cualquier lista de música de YouTube, YouTube Music o programa de podcast que guardaste en la aplicación para que se descargue sola. |
| **Playlist (Lista de reproducción)** | Una colección ordenada de canciones creada en YouTube o YouTube Music. |
| **Playlist "No listada" (*Unlisted*)** | Una lista de YouTube que no es pública en los buscadores, pero que sí permite que Playlist Sync la descargue usando su enlace directo. |
| **Podcast / Feed RSS** | Un programa de audio por episodios (como un programa de radio por internet) que publica capítulos nuevos en una dirección web especial llamada feed RSS. |
| **Archivo `.mp3`** | El archivo de audio de cada canción o episodio ya descargado en tu computadora y listo para sonar sin internet. |
| **Archivo `.m3u8`** | Un pequeño archivo de texto que va dentro de la carpeta de cada lista y le dice al reproductor del celular en qué orden exacto van las canciones. |
| **Etiquetas ID3 (`ID3v2.3`)** | La "ficha de identidad" guardada adentro de cada archivo `.mp3` (nombre de la canción, artista, nombre de la lista como álbum, número de pista y foto de portada). |
| **Identificador externo (`[external_id]`)** | El código único entre corchetes al final del nombre de cada archivo (por ejemplo `[dQw4w9WgXcQ].mp3`) que le permite al programa saber con certeza qué canción ya está descargada sin repetirla nunca. |
| **Servidor local** | El programa de Playlist Sync funcionando en tu propia computadora de casa (sin depender de servidores externos ni de la nube). |
| **Syncthing / Syncthing-Fork** | El programa gratuito que copia automáticamente las carpetas de música desde tu computadora hacia tu celular por el Wi-Fi de tu casa. |
| **Reconciliar con el disco (`Verificar archivos`)** | La función que revisa qué archivos `.mp3` ya tienes guardados en tu carpeta de música y los marca como listos en la base de datos para no volver a descargarlos. |
| **Umbral de seguridad del 50 %** | Un freno automático: si un día YouTube muestra tu lista vacía o con menos de la mitad de tus canciones por un error, Playlist Sync se detiene y no cambia tu lista para proteger tu música. |
| **En vivo (SSE) / Respaldo (5s)** | El indicador que muestra cómo se comunica la página web con tu computadora: *En vivo* significa aviso instantáneo; *Respaldo (5s)* significa que revisa el avance cada 5 segundos. |

