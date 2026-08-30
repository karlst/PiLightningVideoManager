#!/usr/bin/env python3
"""
NetworkManager Wi-Fi startup fallback for Pi Camera Capture.

NetworkManager owns all saved infrastructure Wi-Fi profiles and credentials.
This script does not maintain a second profile list.

At boot:
  1. Give NetworkManager time to autoconnect to any saved Wi-Fi.
  2. If wlan0 has a normal Wi-Fi connection, do nothing.
  3. Otherwise bring up the pre-created "Hotspot" profile.
"""

from __future__ import annotations

import subprocess
import time


HOTSPOT_PROFILE = "Hotspot"
WAIT_SECONDS = 30
POLL_SECONDS = 2


def log(message: str) -> None:
    print(message, flush=True)


def run(command: list[str], timeout: int = 15) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as error:
        return False, str(error)

    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, output


def active_wifi_profile() -> str | None:
    success, output = run(
        [
            "nmcli",
            "-t",
            "-f",
            "NAME,TYPE,DEVICE",
            "connection",
            "show",
            "--active",
        ]
    )

    if not success:
        log(f"nmcli active-connection query failed: {output}")
        return None

    for line in output.splitlines():
        parts = line.split(":", 2)

        if len(parts) != 3:
            continue

        name, connection_type, device = parts

        if connection_type == "802-11-wireless" and device == "wlan0":
            return name

    return None


def main() -> int:
    log("wifiStartup begin")

    run(["nmcli", "radio", "wifi", "on"], timeout=10)

    deadline = time.monotonic() + WAIT_SECONDS

    while time.monotonic() < deadline:
        profile = active_wifi_profile()

        if profile and profile != HOTSPOT_PROFILE:
            log(f"Connected to saved Wi-Fi profile: {profile}")
            return 0

        time.sleep(POLL_SECONDS)

    profile = active_wifi_profile()

    if profile == HOTSPOT_PROFILE:
        log("Hotspot already active")
        return 0

    log("No saved Wi-Fi connected; starting Hotspot")

    success, output = run(
        ["nmcli", "connection", "up", HOTSPOT_PROFILE],
        timeout=40,
    )

    if output:
        log(output)

    if not success:
        log("FAILED to start Hotspot")
        return 1

    log("Hotspot started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
