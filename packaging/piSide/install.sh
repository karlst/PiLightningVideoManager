#!/bin/bash
# PI CAMERA CAPTURE CLEAN INSTALL V1 2026-08-29

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo:"
    echo "  sudo ./install.sh"
    exit 1
fi

INSTALL_USER="${SUDO_USER:-}"
if [ -z "$INSTALL_USER" ] || [ "$INSTALL_USER" = "root" ]; then
    echo "Unable to determine the non-root install user."
    echo "Run as: sudo ./install.sh"
    exit 1
fi

INSTALL_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"
PROGRAM_ROOT="/opt/piCameraCapture"
DATA_ROOT="$INSTALL_HOME/piCameraData"
PACKAGE_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo
echo "Pi Camera Capture installer"
echo "User:         $INSTALL_USER"
echo "Program root: $PROGRAM_ROOT"
echo "Data root:    $DATA_ROOT"
echo

ARCH="$(uname -m)"
case "$ARCH" in
    aarch64|arm64)
        ;;
    *)
        echo "Unsupported architecture: $ARCH"
        echo "This package currently supports 64-bit ARM Raspberry Pi OS."
        exit 1
        ;;
esac

if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found. This installer currently supports Debian/Raspberry Pi OS."
    exit 1
fi

echo "Installing OS dependencies..."
apt-get update
apt-get install -y \
    ffmpeg \
    network-manager \
    python3 \
    python3-flask \
    python3-numpy \
    python3-opencv \
    python3-psutil \
    v4l-utils

echo "Checking Python runtime..."
python3 - <<'PY'
import cv2
import flask
import numpy
import psutil

print("Python imports OK")
print("OpenCV:", cv2.__version__)
print("Flask:", flask.__version__ if hasattr(flask, "__version__") else "installed")
print("NumPy:", numpy.__version__)
print("psutil:", psutil.__version__)
PY

if [ -e "$PROGRAM_ROOT" ]; then
    echo "ERROR: $PROGRAM_ROOT already exists."
    echo "This is a clean installer. Use upgrade.sh for an existing installation."
    exit 1
fi

echo "Installing application..."
mkdir -p "$PROGRAM_ROOT"
cp -a "$PACKAGE_ROOT/app/." "$PROGRAM_ROOT/"

mkdir -p "$PROGRAM_ROOT/config"
cp "$PACKAGE_ROOT/defaults/camera_config.json" "$PROGRAM_ROOT/config/camera_config.json"
cp "$PACKAGE_ROOT/defaults/candidate_config.json" "$PROGRAM_ROOT/config/candidate_config.json"

read -r -p "Camera/site name [$HOSTNAME]: " SITE_NAME
SITE_NAME="${SITE_NAME:-$HOSTNAME}"

python3 - "$PROGRAM_ROOT/config/camera_config.json" "$SITE_NAME" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
site_name = sys.argv[2]

data = json.loads(path.read_text(encoding="utf-8"))
data["camera_site_name"] = site_name
path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
PY

cat > "$PROGRAM_ROOT/config/system_config.json" <<EOF
{
    "home_directory": "$INSTALL_HOME",
    "program_root": "$PROGRAM_ROOT",
    "data_root": "$DATA_ROOT",
    "psf_interval_seconds": 60,
    "save_filtered_false_positives": false
}
EOF

mkdir -p "$DATA_ROOT/captures" "$DATA_ROOT/hls" "$DATA_ROOT/logs"
chown -R "$INSTALL_USER:$INSTALL_USER" "$DATA_ROOT"
chown -R "$INSTALL_USER:$INSTALL_USER" "$PROGRAM_ROOT/config"

echo
echo "Configuring field hotspot..."
DEFAULT_AP_SSID="PiCamera-${HOSTNAME}"

read -r -p "Hotspot SSID [$DEFAULT_AP_SSID]: " AP_SSID
AP_SSID="${AP_SSID:-$DEFAULT_AP_SSID}"

read_masked_password() {
    local prompt="$1"
    local password=""
    local char=""

    printf "%s" "$prompt"

    while true; do
        char=""

        # read returns a non-zero status when Enter terminates an empty
        # one-character read, so do not use read as the while condition.
        IFS= read -r -s -n1 char || true

        case "$char" in
            "")
                break
                ;;
            $'\r'|$'\n')
                break
                ;;
            $'\177'|$'\b')
                if [ -n "$password" ]; then
                    password="${password%?}"
                    printf '\b \b'
                fi
                ;;
            *)
                password+="$char"
                printf '*'
                ;;
        esac
    done

    printf '\n'
    REPLY="$password"
}

while true; do
    read_masked_password "Hotspot password (8+ characters): "
    AP_PASSWORD="$REPLY"

    if [ "${#AP_PASSWORD}" -lt 8 ]; then
        echo "Password must contain at least 8 characters."
        continue
    fi

    read_masked_password "Confirm hotspot password:        "
    AP_PASSWORD_CONFIRM="$REPLY"

    if [ "$AP_PASSWORD" != "$AP_PASSWORD_CONFIRM" ]; then
        echo "Passwords do not match. Try again."
        continue
    fi

    break
done

unset AP_PASSWORD_CONFIRM

if nmcli -t -f NAME connection show | grep -Fxq "Hotspot"; then
    nmcli connection delete Hotspot
fi

nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name Hotspot \
    ssid "$AP_SSID"

nmcli connection modify Hotspot \
    802-11-wireless.mode ap \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$AP_PASSWORD" \
    ipv4.method shared \
    ipv6.method ignore \
    connection.autoconnect no

install -m 755 "$PACKAGE_ROOT/network/wifiStartup.py" /usr/local/lib/piCameraCapture-wifiStartup.py

echo "Installing operator commands..."
for command in "$PACKAGE_ROOT"/bin/*; do
    install -m 755 "$command" "/usr/local/bin/$(basename "$command")"
done

echo "Installing systemd services..."

cat > /etc/systemd/system/wifiStartup.service <<EOF
[Unit]
Description=Pi Camera Capture WiFi Startup Manager
Requires=NetworkManager.service
After=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/piCameraCapture-wifiStartup.py
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/pcm.service <<EOF
[Unit]
Description=Pi Camera Capture WebApp
After=NetworkManager.service wifiStartup.service
Wants=wifiStartup.service

[Service]
Type=simple
User=$INSTALL_USER
WorkingDirectory=$PROGRAM_ROOT
ExecStart=/usr/bin/python3 -m video_capture.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/psf.service <<EOF
[Unit]
Description=Pi Camera Capture SolutionFilter
After=pcm.service
Wants=pcm.service

[Service]
Type=simple
User=$INSTALL_USER
WorkingDirectory=$PROGRAM_ROOT
ExecStart=/usr/bin/python3 -m video_capture.solution_filter_service $DATA_ROOT/captures --interval 60
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wifiStartup.service
systemctl enable pcm.service
systemctl enable psf.service

echo "Validating installed Python source..."
python3 -m compileall -q "$PROGRAM_ROOT"
(
    cd "$PROGRAM_ROOT"
    python3 - <<'PY'
from video_capture.cam_config import CamConfig
from common.candidate_config import CANDIDATE_CONFIG
from common.system_config import load_system_settings

config = CamConfig()
print("CamConfig OK:", config.video_device, config.frame_rate_fps)
print("CandidateConfig OK:", CANDIDATE_CONFIG.sensitivity)
print("SystemConfig OK:", load_system_settings()["program_root"])
PY
)

echo
echo "Installation complete."
echo
echo "Services enabled at boot:"
systemctl is-enabled wifiStartup.service
systemctl is-enabled pcm.service
systemctl is-enabled psf.service
echo
echo "Camera devices currently visible:"
v4l2-ctl --list-devices || true
echo
echo "Next step: connect the camera, then start/reboot and run vmStatus."
