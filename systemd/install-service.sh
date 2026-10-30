#!/usr/bin/env bash
# Instalador del servicio systemd de usuario para Playlist Sync (Linux Mint / Ubuntu)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "=== Instalando servicio de usuario de Playlist Sync en Linux Mint ==="

mkdir -p "${USER_SYSTEMD_DIR}"

# Copiar unidad de servicio
cp "${SCRIPT_DIR}/playlist-sync.service" "${USER_SYSTEMD_DIR}/playlist-sync.service"

# Habilitar persistencia de sesión sin login interactivo (linger)
echo "Habilitando lingering para el usuario actual (${USER})..."
loginctl enable-linger "${USER}" || echo "[AVISO] No se pudo ejecutar loginctl enable-linger, verifica permisos de sudo."

# Recargar daemon de systemd de usuario
systemctl --user daemon-reload

# Habilitar e iniciar servicio
echo "Habilitando y arrancando servicio..."
systemctl --user enable --now playlist-sync.service

echo ""
echo "[OK] Servicio instalado e iniciado con éxito."
echo "Para verificar el estado ejecuta: systemctl --user status playlist-sync.service"
echo "Para ver los registros en tiempo real: journalctl --user -u playlist-sync.service -f"
