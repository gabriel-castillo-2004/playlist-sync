#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
    echo "Error: No se encontró el entorno virtual (.venv)."
    echo "Por favor ejecuta primero: ./install.sh"
    exit 1
fi

echo "Iniciando Playlist Sync..."
exec .venv/bin/python -m playlist_sync.main "$@"

