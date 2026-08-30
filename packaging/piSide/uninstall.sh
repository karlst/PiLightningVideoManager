#!/bin/bash

set -e

APP_NAME="piCameraCapture"
PROGRAM_ROOT="/opt/$APP_NAME"

HELPER_COMMANDS=(
    addWifi
    delWifi
    psfRestart
    psfStart
    psfStop
    vmDisable
    vmEnable
    vmLog
    vmRestart
    vmStart
    vmStatus
    vmStop
)

SERVICES=(
    psf.service
    pcm.service
    wifiStartup.service
)

CLEAN_MODE=false

if [ "$1" = "--clean" ]; then
    CLEAN_MODE=true
elif [ -n "$1" ]; then
    echo "Usage:"
    echo "  sudo ./uninstall.sh"
    echo "  sudo ./uninstall.sh --clean"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: run this script with sudo."
    exit 1
fi

INSTALL_USER="${SUDO_USER:-}"

if [ -z "$INSTALL_USER" ] || [ "$INSTALL_USER" = "root" ]; then
    echo "ERROR: could not determine the non-root install user."
    echo "Run this as:"
    echo "  sudo ./uninstall.sh"
    exit 1
fi

INSTALL_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"

if [ -z "$INSTALL_HOME" ]; then
    echo "ERROR: could not determine home directory for $INSTALL_USER"
    exit 1
fi

DATA_ROOT="$INSTALL_HOME/piCameraData"

echo
echo "Pi Camera Capture uninstall"
echo "---------------------------"
echo "Program root: $PROGRAM_ROOT"
echo "Install user: $INSTALL_USER"
echo "Data root:    $DATA_ROOT"
echo

if $CLEAN_MODE; then
    echo "CLEAN MODE"
    echo
    echo "This will remove:"
    echo "  - Pi Camera Capture program files"
    echo "  - systemd services"
    echo "  - helper commands"
    echo "  - Pi Camera Capture Wi-Fi hotspot profile"
    echo "  - ALL DATA under:"
    echo "      $DATA_ROOT"
    echo
    read -r -p "Type DELETE to continue: " CONFIRM

    if [ "$CONFIRM" != "DELETE" ]; then
        echo "Cancelled."
        exit 0
    fi
else
    echo "Normal uninstall."
    echo "Capture data and logs under $DATA_ROOT will be preserved."
    echo
fi

echo
echo "Stopping services..."

for SERVICE in "${SERVICES[@]}"; do
    systemctl stop "$SERVICE" 2>/dev/null || true
done

echo "Disabling services..."

for SERVICE in "${SERVICES[@]}"; do
    systemctl disable "$SERVICE" 2>/dev/null || true
done

echo "Removing service files..."

for SERVICE in "${SERVICES[@]}"; do
    rm -f "/etc/systemd/system/$SERVICE"
done

systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

echo "Removing program files..."
rm -rf "$PROGRAM_ROOT"

echo "Removing Wi-Fi startup helper..."
rm -f /usr/local/lib/piCameraCapture-wifiStartup.py

echo "Removing helper commands..."

for COMMAND in "${HELPER_COMMANDS[@]}"; do
    rm -f "/usr/local/bin/$COMMAND"
done

echo "Removing Pi Camera Capture hotspot profile..."

if nmcli -t -f NAME connection show 2>/dev/null | grep -Fxq "Hotspot"; then
    nmcli connection delete "Hotspot" >/dev/null 2>&1 || true
fi

if $CLEAN_MODE; then
    echo "Removing Pi Camera Capture data..."
    rm -rf "$DATA_ROOT"
else
    echo "Preserving:"
    echo "  $DATA_ROOT"
fi

echo
echo "Uninstall complete."

if $CLEAN_MODE; then
    echo "Pi Camera Capture program files and data have been removed."
else
    echo "Pi Camera Capture program files have been removed."
    echo "Data remains at:"
    echo "  $DATA_ROOT"
fi

echo
echo "APT-installed system packages were intentionally left installed."