# DELTA FORCE 2
"""
@file analyze_sidecar_timing_DF2.py

@brief Analyze frame timing in Pi Camera Capture JSON sidecars.

For each JSON sidecar in one folder, read frame_records[*].offset_ms and report:

    filename
    trigger_frame
    average_frame_interval_all_ms
    average_frame_interval_le_15ms
    max_frame_interval_ms
    gaps_over_15ms
    first_gap_over_15ms_frame

Output is CSV written to stdout, so it can be viewed directly or redirected
to a file.

Examples:

    python tools\analyze_sidecar_timing_DF2.py E:\captures\captureRepo

    python tools\analyze_sidecar_timing_DF2.py E:\captures\captureRepo > timing.csv

The tool is read-only. It does not modify sidecars.

"first_gap_over_15ms_frame" is the frame AFTER the gap; that is, the frame
whose interval from the preceding frame exceeded 15 ms.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any


GAP_THRESHOLD_MS = 15.0


def read_sidecar(
    sidecar_path: Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            sidecar_path.read_text(
                encoding="utf-8"
            )
        )
    except OSError as error:
        raise RuntimeError(
            f"Unable to read {sidecar_path.name}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid JSON in {sidecar_path.name}: {error}"
        ) from error

    if not isinstance(
        data,
        dict
    ):
        raise RuntimeError(
            f"{sidecar_path.name} does not contain a JSON object"
        )

    return data


def optional_float(
    value: Any,
) -> float | None:
    if (
        value is None or
        value == ""
    ):
        return None

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def optional_int(
    value: Any,
) -> int | None:
    if (
        value is None or
        value == ""
    ):
        return None

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def trigger_frame_number(
    sidecar: dict[str, Any],
) -> int | None:
    candidate = sidecar.get(
        "candidate"
    )

    if isinstance(
        candidate,
        dict
    ):
        trigger_index = optional_int(
            candidate.get(
                "trigger_frame_index"
            )
        )

        if trigger_index is not None:
            return (
                trigger_index +
                1
            )

    trigger_index = optional_int(
        sidecar.get(
            "trigger_frame_index"
        )
    )

    if trigger_index is not None:
        return (
            trigger_index +
            1
        )

    return None


def analyze_sidecar(
    sidecar_path: Path,
) -> tuple[
    int | None,
    float | None,
    float | None,
    float | None,
    int,
    int | None,
]:
    sidecar = read_sidecar(
        sidecar_path
    )

    records = sidecar.get(
        "frame_records"
    )

    if not isinstance(
        records,
        list
    ):
        raise RuntimeError(
            f"{sidecar_path.name} has no frame_records list"
        )

    trigger_frame = trigger_frame_number(
        sidecar
    )

    offsets: list[
        tuple[
            float,
            int,
        ]
    ] = []

    for list_index, record in enumerate(
        records
    ):
        if not isinstance(
            record,
            dict
        ):
            continue

        offset_ms = optional_float(
            record.get(
                "offset_ms"
            )
        )

        if offset_ms is None:
            continue

        frame_number = optional_int(
            record.get(
                "frame_number"
            )
        )

        if frame_number is None:
            frame_number = (
                list_index +
                1
            )

        offsets.append(
            (
                offset_ms,
                frame_number,
            )
        )

    if len(
        offsets
    ) < 2:
        return (
            trigger_frame,
            None,
            None,
            None,
            0,
            None,
        )

    intervals: list[
        tuple[
            float,
            int,
        ]
    ] = [
        (
            offsets[index][0] -
            offsets[index - 1][0],
            offsets[index][1],
        )
        for index in range(
            1,
            len(
                offsets
            )
        )
    ]

    average_interval_all = (
        sum(
            interval
            for interval, _ in intervals
        ) /
        len(
            intervals
        )
    )

    intervals_le_threshold = [
        interval
        for interval, _ in intervals
        if interval <= GAP_THRESHOLD_MS
    ]

    average_interval_le_threshold = (
        sum(
            intervals_le_threshold
        ) /
        len(
            intervals_le_threshold
        )
        if intervals_le_threshold
        else None
    )

    max_interval = max(
        interval
        for interval, _ in intervals
    )

    gaps_over_threshold = sum(
        1
        for interval, _ in intervals
        if interval > GAP_THRESHOLD_MS
    )

    first_gap_frame = next(
        (
            frame_number
            for interval, frame_number in intervals
            if interval > GAP_THRESHOLD_MS
        ),
        None,
    )

    return (
        trigger_frame,
        average_interval_all,
        average_interval_le_threshold,
        max_interval,
        gaps_over_threshold,
        first_gap_frame,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze frame timing in JSON sidecars and write CSV to stdout."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing JSON sidecars to analyze",
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args()

    folder = arguments.folder

    if not folder.is_dir():
        parser.error(
            f"Folder not found: {folder}"
        )

    sidecar_files = sorted(
        folder.glob(
            "*.json"
        )
    )

    writer = csv.writer(
        sys.stdout,
        lineterminator="\n",
    )

    writer.writerow(
        [
            "filename",
            "trigger_frame",
            "average_frame_interval_all_ms",
            "average_frame_interval_le_15ms",
            "max_frame_interval_ms",
            "gaps_over_15ms",
            "first_gap_over_15ms_frame",
        ]
    )

    failed = 0

    for sidecar_path in sidecar_files:
        try:
            (
                trigger_frame,
                average_interval_all,
                average_interval_le_threshold,
                max_interval,
                gaps_over_threshold,
                first_gap_frame,
            ) = analyze_sidecar(
                sidecar_path
            )

            writer.writerow(
                [
                    sidecar_path.name,
                    (
                        trigger_frame
                        if trigger_frame is not None
                        else ""
                    ),
                    (
                        f"{average_interval_all:.3f}"
                        if average_interval_all is not None
                        else ""
                    ),
                    (
                        f"{average_interval_le_threshold:.3f}"
                        if average_interval_le_threshold is not None
                        else ""
                    ),
                    (
                        f"{max_interval:.3f}"
                        if max_interval is not None
                        else ""
                    ),
                    gaps_over_threshold,
                    (
                        first_gap_frame
                        if first_gap_frame is not None
                        else ""
                    ),
                ]
            )

        except RuntimeError as error:
            failed += 1

            print(
                f"WARNING: {error}",
                file=sys.stderr,
            )

    return (
        0
        if failed == 0
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
