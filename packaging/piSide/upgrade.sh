#!/bin/bash
# PI CAMERA CAPTURE UPGRADE V1 2026-08-29
#
# Preserves:
#   /opt/piCameraCapture/config
#   ~/piCameraData and all capture/log data
#   NetworkManager profiles and credentials

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo:"
    echo "  sudo ./upgrade.sh"
    exit 1
fi

PROGRAM_ROOT="/opt/piCameraCapture"
PACKAGE_ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTALL_USER="${SUDO_USER:-}"

if [ -z "$INSTALL_USER" ] || [ "$INSTALL_USER" = "root" ]; then
    echo "Unable to determine the non-root install user."
    echo "Run as: sudo ./upgrade.sh"
    exit 1
fi

INSTALL_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"
DATA_ROOT="$INSTALL_HOME/piCameraData"

BACKUP_ROOT="$(mktemp -d)"
CONFIG_BACKUP="$BACKUP_ROOT/config"

if [ ! -d "$PROGRAM_ROOT" ]; then
    echo "No existing installation found at $PROGRAM_ROOT."
    echo "Use install.sh instead."
    exit 1
fi

echo "Checking upgrade package..."

REQUIRED_PATHS=(
    "$PACKAGE_ROOT/app"
    "$PACKAGE_ROOT/network/wifiStartup.py"
    "$PACKAGE_ROOT/bin"
    "$PACKAGE_ROOT/pcm.service"
    "$PACKAGE_ROOT/psf.service"
)

for required_path in "${REQUIRED_PATHS[@]}"; do
    if [ ! -e "$required_path" ]; then
        echo "ERROR: upgrade package is incomplete."
        echo "Missing:"
        echo "  $required_path"
        exit 1
    fi
done

if [ ! -d "$PROGRAM_ROOT/config" ]; then
    echo "ERROR: existing installation has no config directory:"
    echo "  $PROGRAM_ROOT/config"
    exit 1
fi

echo "Upgrade package check passed."

echo "Stopping services..."
systemctl stop psf.service 2>/dev/null || true
systemctl stop pcm.service 2>/dev/null || true

echo "Preserving configuration..."
cp -a "$PROGRAM_ROOT/config" "$CONFIG_BACKUP"

echo "Replacing application runtime..."
find "$PROGRAM_ROOT" -mindepth 1 -maxdepth 1 ! -name config -exec rm -rf {} +
cp -a "$PACKAGE_ROOT/app/." "$PROGRAM_ROOT/"

rm -rf "$PROGRAM_ROOT/config"
cp -a "$CONFIG_BACKUP" "$PROGRAM_ROOT/config"

echo "Refreshing network startup helper and operator commands..."
install -m 755 "$PACKAGE_ROOT/network/wifiStartup.py" /usr/local/lib/piCameraCapture-wifiStartup.py
for command in "$PACKAGE_ROOT"/bin/*; do
    install -m 755 "$command" "/usr/local/bin/$(basename "$command")"
done

echo "Refreshing systemd services..."
render_service() {
    local source_file="$1"
    local destination_file="$2"

    sed \
        -e "s|@INSTALL_USER@|$INSTALL_USER|g" \
        -e "s|@PROGRAM_ROOT@|$PROGRAM_ROOT|g" \
        -e "s|@DATA_ROOT@|$DATA_ROOT|g" \
        "$source_file" > "$destination_file"
}

render_service \
    "$PACKAGE_ROOT/pcm.service" \
    /etc/systemd/system/pcm.service

render_service \
    "$PACKAGE_ROOT/psf.service" \
    /etc/systemd/system/psf.service

rm -rf "$BACKUP_ROOT"

systemctl daemon-reload

echo "Starting services..."
systemctl start pcm.service
systemctl start psf.service

echo
echo "Upgrade complete."
systemctl is-active pcm.service || true
systemctl is-active psf.service || true
