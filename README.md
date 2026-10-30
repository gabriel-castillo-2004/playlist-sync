# Playlist Sync

Aplicación web local y ligera para descargar y mantener al día playlists públicas de YouTube, YouTube Music y podcasts como archivos MP3 con portadas y etiquetas ID3, listos para reproducir en cualquier celular o equipo mediante Syncthing.

---

## ⚠️ Advertencia legal y de uso

Este proyecto ha sido desarrollado exclusivamente para **uso personal y educativo**. La descarga de audio de plataformas como YouTube puede infringir los términos de servicio del proveedor de contenido. Esta herramienta no facilita la distribución pública ni la compartición de material con derechos de autor.

---

## 📌 Arquitectura y Reglas Importantes de Operación

1. **Un solo servidor activo a la vez:**
   - **Nunca** ejecutes simultáneamente dos instancias del servidor de Playlist Sync apuntando a la misma carpeta de música (ya sea compartida por red o sincronizada mediante Syncthing).
2. **Base de datos local independiente:**
   - Cada máquina mantiene su propia base de datos SQLite local (`playlist_sync.sqlite3`).
3. **Migración entre equipos:**
   - Para cambiar de máquina o respaldar tus suscripciones sin conflictos en la base de datos, se exporta/importa el archivo `sources.json`.
4. **Soporte multiplataforma:**
   - Totalmente compatible tanto con **Linux Mint 22.3 / Ubuntu 24.04** como con **Windows 11**.

---

## 📋 Requisitos del sistema

- **Python 3.12+**
- **ffmpeg** (para conversión y remuxing de audio)
- **Deno** (o Node.js) como motor de JavaScript para resolver retos de YouTube en `yt-dlp`
- **Espacio en disco:** Mínimo 1 GB libre (o según el tamaño de tu colección)

---

## 🚀 Instalación rápida

### En Linux (Linux Mint 22.3 / Ubuntu 24.04)

Debido a las restricciones de PEP 668 en Ubuntu 24.04, el instalador crea y utiliza automáticamente un entorno virtual (`.venv`):

```bash
git clone <url-del-repo> playlist-sync
cd playlist-sync
chmod +x install.sh start.sh
./install.sh
```

El script `install.sh` instala `python3-venv` y `ffmpeg` con `apt`, instala `Deno` si hace falta, crea el entorno virtual, instala las dependencias de Python con `pip` dentro del venv y ejecuta el diagnóstico de salud (`doctor`).

Para arrancar el servidor:
```bash
./start.sh
```

*(En la Fase 6 se documentará el servicio de usuario con `systemd` y `loginctl enable-linger`).*

### En Windows 11

Abre PowerShell en la carpeta del repositorio y ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Para arrancar el servidor:
```cmd
start.bat
```

---

## 🩺 Diagnóstico de Salud del Sistema (Doctor)

Para comprobar en cualquier momento que todos los componentes requeridos y opcionales están instalados y funcionando:

**En Linux / macOS:**
```bash
.venv/bin/python -m playlist_sync.doctor
```

**En Windows:**
```powershell
.\.venv\Scripts\python.exe -m playlist_sync.doctor
```

---

## 🧪 Pruebas y Control de Calidad

Los comandos estándar de desarrollo se ejecutan dentro del entorno virtual:

```bash
# Ejecutar suite de pruebas unitarias e integración
pytest

# Cobertura de código del núcleo (core/)
pytest --cov=src/playlist_sync/core

# Linter de código (Ruff)
ruff check .

# Formato de código (Ruff)
ruff format --check .

# Verificación de tipos estáticos
mypy src/playlist_sync/core
```

---

## 📊 Estado de configuración del proyecto (Tabla 1.4)

| Dato | Valor / Estado |
|---|---|
| Sistema operativo en producción | Linux Mint 22.3 (base Ubuntu 24.04 LTS "noble") |
| Sistema operativo en desarrollo | Windows 11 |
| Versión de Python objetivo | Python 3.12.3 (producción y desarrollo) |
| ¿PC siempre encendida o bajo demanda? | *Por confirmar por el dueño al requerirlo* |
| Playlists públicas pequeñas para pruebas | *Por confirmar por el dueño al requerirlo* |
| Podcasts para pruebas (RSS y YouTube) | *Por confirmar por el dueño al requerirlo* |
| Reproductor de música en el celular | *Por confirmar por el dueño al requerirlo* |
| Carpeta de destino de la música | Configurable en `config.toml` (`music_root`) |
| Espacio libre en disco | Verificado por `doctor.py` dinámicamente |

