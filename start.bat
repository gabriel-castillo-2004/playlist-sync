@echo off
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual en .venv.
    echo Por favor ejecuta primero: powershell -ExecutionPolicy Bypass -File .\install.ps1
    pause
    exit /b 1
)

echo [1/2] Verificando actualizacion del motor de descargas (RF-16)...
".venv\Scripts\pip.exe" install --upgrade --no-input yt-dlp >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [AVISO] No se pudo actualizar yt-dlp automaticamente; continuando con la version local instalada.
) else (
    echo [OK] Motor yt-dlp al dia.
)

echo [2/2] Iniciando Playlist Sync...
if "%~1"=="" (
    ".venv\Scripts\python.exe" -m playlist_sync.main serve
) else (
    ".venv\Scripts\python.exe" -m playlist_sync.main %*
)
