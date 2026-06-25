#!/usr/bin/env python3

import subprocess
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

KNOWN_WIFI_FILE = BASE_DIR / "wifiProfiles.txt"
LOG_FILE = BASE_DIR / "wifiStartup.log"

AP_PROFILE = "Hotspot"
AP_SSID = "PiCamera3709"

USER_NAME = "karlst"
WEB_PORT = 8080


def log(message: str = "") -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"

    print(line, flush=True)

    with LOG_FILE.open("a") as file:
        file.write(line + "\n")


def run_command(command: list[str], timeout_seconds: int = 30) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            timeout=timeout_seconds,
            text=True,
            capture_output=True
        )

        output = (
            (result.stdout or "") +
            (result.stderr or "")
        ).strip()

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Command timed out"

    except Exception as error:
        return False, str(error)


def read_profiles() -> list[str]:
    profiles: list[str] = []

    if not KNOWN_WIFI_FILE.exists():
        raise FileNotFoundError(f"Known WiFi file not found: {KNOWN_WIFI_FILE}")
    

    for line in KNOWN_WIFI_FILE.read_text().splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        profiles.append(line)

    return profiles


def try_profile(profile: str) -> bool:
    log(f"Trying WiFi profile: {profile}")

    success, output = run_command(
        [
            "nmcli",
            "connection",
            "up",
            profile
        ],
        timeout_seconds=40
    )

    if output:
        log(output)

    if success:
        log(f"Connected using profile: {profile}")
    else:
        log(f"Failed profile: {profile}")

    return success


def start_ap() -> bool:
    log(f"Starting AP profile: {AP_PROFILE}")

    success, output = run_command(
        [
            "nmcli",
            "connection",
            "up",
            AP_PROFILE
        ],
        timeout_seconds=40
    )

    if output:
        log(output)

    if success:
        log(f"AP started: {AP_SSID}")
    else:
        log("FAILED to start AP")

    return success


def get_ip_addresses() -> list[str]:
    success, output = run_command(
        [
            "hostname",
            "-I"
        ],
        timeout_seconds=5
    )

    if not success:
        return []

    return [
        item.strip()
        for item in output.split()
        if item.strip()
    ]


def get_tailscale_ips() -> list[str]:
    success, output = run_command(
        [
            "tailscale",
            "ip"
        ],
        timeout_seconds=5
    )

    if not success:
        return []

    return [
        item.strip()
        for item in output.splitlines()
        if item.strip()
    ]


def log_access_info() -> None:
    ip_addresses = get_ip_addresses()
    tailscale_ips = get_tailscale_ips()

    log("")
    log("Access info:")

    if ip_addresses:
        log("Local IP addresses:")

        for ip_address in ip_addresses:
            log(f"    {ip_address}")
            log(f"    Web: http://{ip_address}:{WEB_PORT}")
            log(f"    SSH: ssh {USER_NAME}@{ip_address}")
    else:
        log("Local IP addresses: none found")

    if tailscale_ips:
        log("Tailscale: connected")

        for ip_address in tailscale_ips:
            log(f"    {ip_address}")
            log(f"    Web: http://{ip_address}:{WEB_PORT}")
            log(f"    SSH: ssh {USER_NAME}@{ip_address}")
    else:
        log("Tailscale: not connected")


def main() -> int:
    log("")
    log("========================================")
    log("wifiStartup begin")
    log("========================================")

    success, output = run_command(
        [
            "nmcli",
            "radio",
            "wifi",
            "on"
        ],
        timeout_seconds=10
    )

    if output:
        log(output)

    connected = False

    try:
        profiles = read_profiles()
    except FileNotFoundError as e:
        log(f"Error: {e}")
        return 1    
    
    # for profile in profiles:
    #     print(profile)

    for profile in profiles:
        if try_profile(profile):
            connected = True
            break

    if not connected:
        log("No known WiFi profile connected")

        connected = start_ap()

    log_access_info()

    if connected:
        log("wifiStartup complete")
        log("========================================")
        return 0

    log("wifiStartup FAILED")
    log("========================================")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())