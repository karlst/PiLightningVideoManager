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

            run_batch_solution_filter(
                arguments.folder,
                verbosity=arguments.verbosity,
                delete_rejects=(
                    not save_false_positives
                ),
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
