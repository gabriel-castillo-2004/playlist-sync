@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual en .venv.
    echo Por favor ejecuta primero: powershell -ExecutionPolicy Bypass -File .\install.ps1
    pause
    exit /b 1
)

echo Iniciando Playlist Sync...
".venv\Scripts\python.exe" -m playlist_sync.main %*

