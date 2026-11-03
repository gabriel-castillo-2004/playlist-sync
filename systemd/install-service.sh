#!/usr/bin/env bash
# Instalador del servicio systemd de usuario para Playlist Sync (Linux Mint / Ubuntu)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
USER_SYSTEMD_DIR="${USER_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
CURRENT_USER="${USER:-$(id -un)}"

echo "=== Instalando servicio de usuario de Playlist Sync en Linux Mint ==="

mkdir -p "${USER_SYSTEMD_DIR}"

# Generar unidad de servicio sustituyendo la ruta del repositorio dinámicamente
echo "Configurando ruta del repositorio: ${REPO_DIR}..."
ESCAPED_REPO_DIR=$(printf '%s\n' "${REPO_DIR}" | sed -e 's/[\\|&]/\\&/g')
sed "s|%h/playlist-sync|${ESCAPED_REPO_DIR}|g" "${SCRIPT_DIR}/playlist-sync.service" > "${USER_SYSTEMD_DIR}/playlist-sync.service"

if [ "${INSTALL_SERVICE_ONLY:-0}" = "1" ]; then
    echo "[OK] Archivo de servicio generado exitosamente en ${USER_SYSTEMD_DIR}/playlist-sync.service"
    exit 0
fi

# Habilitar persistencia de sesión sin login interactivo (linger)
echo "Habilitando lingering para el usuario actual (${CURRENT_USER})..."
loginctl enable-linger "${CURRENT_USER}" || echo "[AVISO] No se pudo ejecutar loginctl enable-linger, verifica permisos de sudo."

# Recargar daemon de systemd de usuario
systemctl --user daemon-reload

# Habilitar e iniciar servicio
echo "Habilitando y arrancando servicio..."
systemctl --user enable --now playlist-sync.service

echo ""
echo "[OK] Servicio instalado e iniciado con éxito."
echo "Para verificar el estado ejecuta: systemctl --user status playlist-sync.service"
echo "Para ver los registros en tiempo real: journalctl --user -u playlist-sync.service -f"
