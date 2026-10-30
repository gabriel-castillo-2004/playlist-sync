#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
    echo "Error: No se encontró el entorno virtual (.venv)."
    echo "Por favor ejecuta primero: ./install.sh"
    exit 1
fi

echo "[1/2] Verificando actualización del motor de descargas (RF-16)..."
.venv/bin/pip install --upgrade --no-input yt-dlp >/dev/null 2>&1 || echo "[AVISO] No se pudo actualizar yt-dlp automáticamente; continuando con la versión instalada."

echo "[2/2] Iniciando Playlist Sync..."
if [ $# -eq 0 ]; then
    exec .venv/bin/python -m playlist_sync.main serve
else
    exec .venv/bin/python -m playlist_sync.main "$@"
fi
