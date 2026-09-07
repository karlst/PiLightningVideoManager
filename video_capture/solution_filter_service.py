"""
Run Pi-side SolutionFilter classification periodically.

This small service runner deliberately reuses SolutionFilter batch engine rather than
creating another classification path. Every interval it scans the capture
folder. TRUE_FLASH pairs are renamed from trigger_* to flash_* and remain in
the capture folder. Rejected Candidate pairs are either moved to anomaly
folders or deleted according to system_config.json.

The capture application and this process remain independent; Linux schedules
them separately.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import subprocess
import sys
import time

from common.solution_batch import run_batch_solution_filter
from common.system_config import load_system_settings


_running = True


def _stop(
    signum,
    frame,
) -> None:
    global _running
    _running = False


def networkmanager_ap_active(
    device: str = "wlan0",
) -> bool:
    """Return True when NetworkManager has the Wi-Fi device in AP mode.

    A field camera serving its fallback access point is treated as offline for
    S3 purposes.  This check is intentionally performed once per PSF pass, not
    once per capture and not only at process startup.
    """
    try:
        connection_result = subprocess.run(
            [
                "nmcli",
                "-g",
                "GENERAL.CONNECTION",
                "device",
                "show",
                device,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=3.0,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        raise RuntimeError(
            f"Unable to query NetworkManager for {device}: {error}"
        ) from error

    if connection_result.returncode != 0:
        detail = (
            connection_result.stderr.strip()
            or connection_result.stdout.strip()
            or f"nmcli returned {connection_result.returncode}"
        )
        raise RuntimeError(
            f"Unable to query NetworkManager for {device}: {detail}"
        )

    connection_name = (
        connection_result.stdout.strip()
    )

    if (
        not connection_name
        or connection_name == "--"
    ):
        return False

    try:
        mode_result = subprocess.run(
            [
                "nmcli",
                "-g",
                "802-11-wireless.mode",
                "connection",
                "show",
                connection_name,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=3.0,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        raise RuntimeError(
            f"Unable to query NetworkManager mode for "
            f"{connection_name!r}: {error}"
        ) from error

    if mode_result.returncode != 0:
        detail = (
            mode_result.stderr.strip()
            or mode_result.stdout.strip()
            or f"nmcli returned {mode_result.returncode}"
        )
        raise RuntimeError(
            f"Unable to query NetworkManager mode for "
            f"{connection_name!r}: {detail}"
        )

    return (
        mode_result.stdout.strip().lower()
        == "ap"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Periodically run Pi-side SolutionFilter classification."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Pi capture folder containing Candidate MP4/JSON pairs",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help=(
            "Seconds between SolutionFilter batch engine runs "
            "(default: 60)"
        ),
    )

    parser.add_argument(
        "-v",
        "--verbosity",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="SolutionFilter batch engine verbosity",
    )

    arguments = parser.parse_args()

    if arguments.interval <= 0.0:
        print("Interval must be greater than zero.")
        return 1

    signal.signal(
        signal.SIGTERM,
        _stop,
    )
    signal.signal(
        signal.SIGINT,
        _stop,
    )

    while _running:
        started = time.monotonic()

        try:
            # Reload system_config.json on every pass so a web-UI change
            # takes effect without restarting the independent PSF service.
            system_settings = (
                load_system_settings()
            )

            save_false_positives = bool(
                system_settings.get(
                    "save_filtered_false_positives",
                    False,
                )
            )

            configured_upload_to_s3 = bool(
                system_settings.get(
                    "upload_to_s3",
                    False,
                )
            )

            # Check NetworkManager once per PSF pass.  A field camera serving
            # its fallback AP is intentionally treated as offline: do not even
            # attempt S3.  If the AP disappears later, the next pass notices
            # automatically and resumes normal upload behavior.
            try:
                ap_active = (
                    networkmanager_ap_active()
                )
            except RuntimeError as error:
                # Fail safe: if AP state cannot be determined, do not blindly
                # attempt S3.  True flashes will remain pending locally.
                ap_active = True

                print(
                    f"PSF network-mode check failed; "
                    f"treating camera as offline: {error}",
                    file=sys.stderr,
                    flush=True,
                )

            effective_upload_to_s3 = (
                configured_upload_to_s3
                and not ap_active
            )

            # In AP/offline field mode, retain true flashes for later upload
            # but delete recognized anomalies / rejects so storage does not
            # fill with known false positives.  When not in AP mode, preserve
            # the configured false-positive retention behavior.
            delete_rejects = (
                True
                if ap_active
                else not save_false_positives
            )

            run_batch_solution_filter(
                arguments.folder,
                verbosity=arguments.verbosity,
                delete_rejects=delete_rejects,
                upload_to_s3=effective_upload_to_s3,
            )
        except Exception as error:
            print(
                f"SolutionFilter service pass failed: {error}",
                file=sys.stderr,
                flush=True,
            )

        elapsed = (
            time.monotonic() -
            started
        )

        remaining = max(
            0.0,
            arguments.interval - elapsed,
        )

        deadline = (
            time.monotonic() +
            remaining
        )

        while _running:
            sleep_time = (
                deadline -
                time.monotonic()
            )

            if sleep_time <= 0.0:
                break

            time.sleep(
                min(
                    sleep_time,
                    1.0,
                )
            )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
