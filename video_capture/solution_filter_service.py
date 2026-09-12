"""
Run Pi-side capture classification periodically.

This service reuses common.solution_batch so the Pi has one production
classification path.  Each pass scans pending capture_* pairs, applies the
frozen logistic FLASH/ANOMALY classifier, optionally uploads eligible pairs to
S3, and applies the configured false-positive retention policy.  The legacy
SolutionFilter is not part of this production path.

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
from threading import Lock, Thread

from common.solution_batch import run_batch_solution_filter
from common.runtime_telemetry import RollingEventCounts
from common.runtime_telemetry import atomic_write_json
from common.runtime_telemetry import utc_now_text
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

    runtime_counts = RollingEventCounts(
        ("flash", "anomaly", "s3_success", "s3_failure"),
        bucket_seconds=5 * 60,
        window_hours=24,
    )
    runtime_status_path = Path(
        "/run/psf/psf_status.json"
    )
    runtime_state_lock = Lock()
    runtime_state = {
        "ap_active": None,
        "configured_upload_to_s3": False,
        "effective_upload_to_s3": False,
        "last_classification_utc": None,
        "last_upload_utc": None,
        "last_pass_utc": None,
        "last_error": "",
    }

    def publish_runtime_status() -> None:
        while _running:
            try:
                with runtime_state_lock:
                    state = dict(runtime_state)

                atomic_write_json(
                    runtime_status_path,
                    {
                        "schema_version": 1,
                        "component": "psf",
                        "heartbeat_utc": utc_now_text(),
                        **state,
                        **runtime_counts.snapshot(),
                    },
                )
            except Exception:
                # Runtime status is diagnostic only. If /run/psf is absent
                # during development, or publishing otherwise fails, PSF must
                # continue classifying captures.
                pass

            time.sleep(5.0)

    Thread(
        target=publish_runtime_status,
        name="PsfRuntimeStatus",
        daemon=True,
    ).start()

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

            with runtime_state_lock:
                runtime_state["ap_active"] = ap_active
                runtime_state["configured_upload_to_s3"] = (
                    configured_upload_to_s3
                )
                runtime_state["effective_upload_to_s3"] = (
                    effective_upload_to_s3
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

            batch_summary = run_batch_solution_filter(
                arguments.folder,
                verbosity=arguments.verbosity,
                delete_rejects=delete_rejects,
                upload_to_s3=effective_upload_to_s3,
                return_summary=True,
            )

            flash_count = int(batch_summary.get("flash", 0))
            anomaly_count = int(batch_summary.get("anomaly", 0))
            s3_success_count = int(batch_summary.get("s3_success", 0))
            s3_failure_count = int(batch_summary.get("s3_failure", 0))

            runtime_counts.increment("flash", flash_count)
            runtime_counts.increment("anomaly", anomaly_count)
            runtime_counts.increment("s3_success", s3_success_count)
            runtime_counts.increment("s3_failure", s3_failure_count)

            now_utc = utc_now_text()
            with runtime_state_lock:
                runtime_state["last_pass_utc"] = now_utc
                runtime_state["last_error"] = ""
                if flash_count or anomaly_count:
                    runtime_state["last_classification_utc"] = now_utc
                if s3_success_count:
                    runtime_state["last_upload_utc"] = now_utc

        except Exception as error:
            with runtime_state_lock:
                runtime_state["last_pass_utc"] = utc_now_text()
                runtime_state["last_error"] = str(error)

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
