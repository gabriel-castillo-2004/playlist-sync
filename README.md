# Playlist Sync 🎵

Aplicación web local y ligera para descargar y mantener al día playlists públicas de YouTube, YouTube Music y podcasts como archivos MP3 con carátulas embebidas y etiquetas ID3, listos para reproducir en cualquier celular o equipo mediante Syncthing.

---

## ⚠️ Advertencia legal y de uso

Este proyecto ha sido desarrollado exclusivamente para **uso personal y educativo**. La descarga de audio de plataformas como YouTube puede infringir los términos de servicio del proveedor de contenido. Esta herramienta no facilita la distribución pública ni la compartición de material con derechos de autor.

---

## 📌 Arquitectura y Reglas Importantes de Operación

1. **Un solo servidor activo a la vez:**
   - **Nunca** ejecutes simultáneamente dos instancias del servidor de Playlist Sync sobre la misma carpeta de música (ya sea compartida en red local o sincronizada mediante Syncthing).
2. **Base de datos local independiente:**
   - Cada máquina mantiene su propia base de datos SQLite local (`playlist_sync.sqlite3`).
3. **Migración entre equipos mediante `sources.json`:**
   - Para cambiar de equipo, respaldar suscripciones o sincronizar listas entre máquinas, utiliza el comando `export` e `import` que genera un archivo portátil `sources.json`.
4. **Soporte multiplataforma garantizado:**
   - Totalmente funcional y probado en **Linux Mint 22.3 / Ubuntu 24.04 LTS** y en **Windows 11** con Python 3.12.

---

## 📋 Requisitos del sistema

- **Python 3.12+**
- **ffmpeg** (para conversión y remuxing de audio a MP3)
- **Deno** (o Node.js) como intérprete de JavaScript para resolver retos de YouTube en `yt-dlp`
- **Espacio en disco:** Mínimo 1 GB libre (ajustable en `config.toml`)

---

## 🚀 Instalación y Puesta en Marcha

### En Linux Mint 22.3 / Ubuntu 24.04 (Producción)

Debido a las restricciones de PEP 668 en Ubuntu 24.04, el script `install.sh` instala las dependencias de sistema mediante `apt` y configura un entorno virtual `.venv`:

```bash
git clone <url-del-repo> playlist-sync
cd playlist-sync
chmod +x install.sh start.sh systemd/install-service.sh
./install.sh
```

#### Servicio de arranque automático en Linux Mint (Systemd de usuario)
Para que el servidor se ejecute siempre en segundo plano, arranque automáticamente con el sistema y persista incluso sin iniciar sesión gráfica:

```bash
./systemd/install-service.sh
```

Este script:
1. Copia la unidad de servicio `playlist-sync.service` a `~/.config/systemd/user/`.
2. Habilita la persistencia con `loginctl enable-linger $USER`.
3. Activa y arranca el servicio con `systemctl --user enable --now playlist-sync.service`.

Comandos de gestión del servicio:
- Ver estado: `systemctl --user status playlist-sync.service`
- Ver registros en vivo: `journalctl --user -u playlist-sync.service -f`
- Reiniciar: `systemctl --user restart playlist-sync.service`
- Detener: `systemctl --user stop playlist-sync.service`

---

### En Windows 11 (Desarrollo o Servidor)

1. Abre PowerShell en la carpeta del proyecto y ejecuta:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

2. Para iniciar el servidor manualmente:
```cmd
start.bat
```
*(El script `start.bat` verifica automáticamente actualizaciones de `yt-dlp` al arrancar e inicia el servidor en `http://localhost:8000`).*

#### Arranque automático en Windows (Opcional)
Para iniciar Playlist Sync al encender tu PC en Windows:
- Presiona `Win + R`, escribe `shell:startup` y presiona Enter.
- Crea un acceso directo a `start.bat` dentro de esa carpeta.

---

## 📱 Interfaz Web "A prueba de mamá"

Abre en tu navegador local:
```
http://localhost:8000
```

### Acceso desde el celular u otros equipos en la red local (LAN / Wi-Fi)
Por defecto, el servidor escucha únicamente en `127.0.0.1` (acceso exclusivo desde la misma PC). Para abrir la interfaz desde tu celular en la misma red Wi-Fi:
1. En `config.toml`, cambia `host = "127.0.0.1"` por `host = "0.0.0.0"` (o inicia el servidor con `python -m playlist_sync serve --host 0.0.0.0 --port 8000`).
2. Consulta la IP local de tu PC (ej. `ip -4 addr` en Linux o `ipconfig` en Windows) y abre en el navegador del celular `http://<IP-DE-TU-PC>:8000` (por ejemplo, `http://192.168.1.50:8000`).

> **⚠️ Advertencia de seguridad en red local:** Playlist Sync está diseñado para operar dentro de una red doméstica de confianza y **no incluye autenticación de usuarios**. Expón `0.0.0.0` únicamente en tu Wi-Fi privado de casa; nunca expongas el puerto `8000` a internet público ni en redes Wi-Fi abiertas.

Características principales:
- **Pantalla única:** Diseñada para usarse con una sola mano en pantallas móviles (mínimo 360 px).
- **Sin jerga técnica:** Estados en español claro ("Al día ✓", "3 nuevas — Descargar", "Descargando...", "Hubo un problema").
- **Progreso reactivo en vivo:** Conexión continua vía Server-Sent Events (SSE) con respaldo automático por polling si se interrumpe la red.
- **Búsqueda y agregación inteligente:** La caja de entrada acepta:
  - Enlaces de playlists de YouTube / YouTube Music.
  - Enlaces directos a feeds RSS de podcasts.
  - Nombre o temática de un podcast (búsqueda automática en el catálogo público de iTunes).
- **Modo oscuro automático:** Se adapta al tema de tu sistema operativo (`prefers-color-scheme`).
- **Instalable como PWA:** Guárdala directamente en la pantalla de inicio de tu celular.

---

## 🔄 Migración de Fuentes entre Equipos (`sources.json`)

Para mover tus listas a una computadora nueva sin transferir bases de datos SQLite binarias:

1. **En la PC de origen:**
   ```bash
   python -m playlist_sync export
   # o: python scripts/migrate_sources.py export
   ```
   Esto genera el archivo portátil `sources.json`.

2. **En la PC de destino:**
   Copia el archivo `sources.json` al nuevo equipo y ejecuta:
   ```bash
   python -m playlist_sync import sources.json
   # o: python scripts/migrate_sources.py import sources.json
   ```
   El sistema registrará todas las fuentes de manera idempotente sin duplicar carpetas existentes.

---

## 📲 Sincronización con el Celular (Syncthing)

Playlist Sync organiza la música descargada en carpetas locales con carátulas `cover.jpg` y playlists relativas `.m3u8`.

Para transferir los archivos automáticamente a tu celular:
1. Consulta la guía detallada e ilustrada en: [`docs/syncthing.md`](docs/syncthing.md).
2. **Regla de oro:**
   - Carpeta en la PC: **"Solo enviar"** (*Send Only*).
   - Carpeta en el celular: **"Solo recibir"** (*Receive Only*).
3. Abre tu reproductor favorito en el celular (Musicolet, AIMP, Poweramp, VLC) y tus playlists y podcasts estarán organizados con carátulas de alta calidad.

---

## 🛠️ Comandos de Línea de Comandos (CLI)

El CLI ofrece control total para entornos sin interfaz gráfica o automatizaciones:

```bash
# Diagnóstico de salud del sistema
python -m playlist_sync doctor

# Iniciar servidor web (FastAPI + SSE)
python -m playlist_sync serve [--host 0.0.0.0] [--port 8000]

# Registrar una nueva playlist o podcast
python -m playlist_sync add "https://music.youtube.com/playlist?list=..."

# Sincronizar una fuente específica o todas
python -m playlist_sync sync 1
python -m playlist_sync sync all

# Consultar estado de todas las fuentes
python -m playlist_sync status

# Exportar e importar fuentes
python -m playlist_sync export [archivo.json]
python -m playlist_sync import [archivo.json]

# Crear un respaldo consistente de la base de datos
python -m playlist_sync backup [--dir backups]

# Restaurar la base de datos desde un respaldo previo (H-02)
python -m playlist_sync restore-backup backups/playlist_sync_backup_YYYYMMDD_HHMMSS_ffffff.sqlite3

# Reconciliar el estado de la base de datos con los archivos MP3 ya existentes en disco (RF-20)
python -m playlist_sync reconcile [all | <id_fuente>]
```

---

## 🧪 Pruebas y Control de Calidad

Ejecuta la batería completa de pruebas automáticas dentro del entorno virtual:

```bash
# Suite completa de pruebas unitarias e integración
pytest

# Cobertura de código del núcleo (core/)
pytest --cov=src/playlist_sync/core --cov-report=term-missing

# Verificación de linters y estilo
ruff check .
ruff format --check .

# Verificación estricta de tipos
mypy src/playlist_sync
```

---

## ⚙️ Configuración (`config.toml`)

El archivo `config.toml` permite ajustar el comportamiento del servidor:

```toml
[server]
host = "127.0.0.1"
port = 8000
log_level = "INFO"
log_file = "playlist_sync.log"

[storage]
music_root = "music_root"
database_path = "playlist_sync.sqlite3"
min_disk_free_mb = 1024

[sync]
interval_hours = 6             # Revisión automática cada N horas (0 = desactivado)
max_retries = 3                # Reintentos por canción fallida
safety_threshold = 0.50        # Protección contra encogimiento repentino de playlists
concurrency = 1                # Descargas secuenciales para cuidar hardware modesto
sleep_interval = 2.0           # Pausa en segundos entre descargas de canciones (H-17)
sleep_interval_requests = 1.0  # Pausa en segundos entre peticiones de metadatos a YouTube
rate_limit_bytes = 0           # Límite de velocidad en bytes/s (0 = sin límite)
```
