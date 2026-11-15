#!/usr/bin/env bash
# Script pemasangan otomatis systemd user service untuk Orca ADE Antigravity Auto-Switcher

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="orca-agy-rotator.service"
TARGET_SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

echo "=========================================================="
echo "   Pemasangan Orca ADE Antigravity Auto-Switcher Service"
echo "=========================================================="

mkdir -p "${SYSTEMD_USER_DIR}"

PYTHON_BIN="$(which python3)"
if [ -z "${PYTHON_BIN}" ]; then
    echo "[ERROR] Python 3 tidak ditemukan di sistem."
    exit 1
fi

cat <<EOF > "${TARGET_SERVICE_FILE}"
[Unit]
Description=Orca ADE Antigravity Auto-Switcher Daemon
After=graphical-session.target network.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} "${SCRIPT_DIR}/main.py" run
WorkingDirectory=${SCRIPT_DIR}
Restart=always
RestartSec=5
Environment="PATH=${PATH}"
Environment="DISPLAY=:0"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${UID}/bus"

[Install]
WantedBy=default.target
EOF

echo "[1/3] File unit service dibuat di: ${TARGET_SERVICE_FILE}"

echo "[2/3] Memperbarui konfigurasi systemd user daemon..."
systemctl --user daemon-reload

echo "[3/3] Mengaktifkan dan menjalankan service..."
systemctl --user enable --now "${SERVICE_NAME}"

echo "----------------------------------------------------------"
echo "Status Service:"
systemctl --user status "${SERVICE_NAME}" --no-pager || true
echo "----------------------------------------------------------"
echo "Pemasangan selesai! Service sekarang berjalan di background."
echo "Untuk melihat log service: journalctl --user -u ${SERVICE_NAME} -f"
echo "Untuk menghentikan:        systemctl --user stop ${SERVICE_NAME}"
