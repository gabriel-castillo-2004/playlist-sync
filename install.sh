#!/usr/bin/env bash
set -euo pipefail

echo "=================================================="
echo " Playlist Sync — Instalador para Linux (Mint / Ubuntu)"
echo "=================================================="

# 1. Comprobar permisos y paquetes del sistema
echo "[1/5] Verificando e instalando paquetes del sistema (apt)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl
else
    echo "Aviso: 'apt-get' no disponible. Asegúrate de tener python3-venv y ffmpeg instalados manualmente."
fi

# 2. Instalar Deno si no está presente (recomendado por yt-dlp)
echo "[2/5] Verificando runtime Deno..."
if ! command -v deno >/dev/null 2>&1; then
    echo "Instalando Deno con el instalador oficial..."
    curl -fsSL https://deno.land/install.sh | sh
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
else
    echo "Deno ya está instalado."
fi

# 3. Crear entorno virtual (PEP 668 en Ubuntu 24.04 / Mint 22)
echo "[3/5] Configurando entorno virtual (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# 4. Instalar dependencias con pip dentro del venv
echo "[4/5] Instalando dependencias de Python dentro del venv..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# 5. Ejecutar diagnóstico de salud del sistema
echo "[5/5] Ejecutando verificación del sistema (doctor)..."
.venv/bin/python -m playlist_sync.doctor

echo ""
echo "¡Instalación completada! Puedes iniciar la aplicación con ./start.sh"

