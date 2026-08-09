"""
@file batch_classifier.py

@brief Batch-classify Candidate captures and move MP4/JSON pairs into subfolders.

Each Candidate consists of an MP4 plus its matching JSON sidecar. The utility
runs the desktop SolutionFilter for every Candidate in the requested folder,
then moves the pair into a classification subfolder.

Existing destination files are never overwritten. If either member of a
capture pair would collide with an existing destination filename, that entire
capture is skipped and batch processing continues with the next file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_types import CATEGORY_BRIGHT_NOISE
from video_analyzer.solution_types import CATEGORY_FRAME_DROPOUT
from video_analyzer.solution_types import CATEGORY_STEADY_STATE_CHANGE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH


DESTINATION_FOLDERS = {
    CATEGORY_TRUE_FLASH: "true_flashes",
    CATEGORY_FRAME_DROPOUT: "frame_dropout_anomalies",
    CATEGORY_BRIGHT_NOISE: "bright_noise_anomalies",
    CATEGORY_STEADY_STATE_CHANGE: "steady_state_anomalies",
    "UNCLASSIFIED": "unclassified",
}


def read_sidecar(
    sidecar_path: Path,
) -> dict[str, Any]:
    with sidecar_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        sidecar = json.load(file)

    if not isinstance(sidecar, dict):
        raise RuntimeError(
            "Sidecar root must be a JSON object"
        )

    return sidecar


def build_metric_arrays(
    sidecar: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    records = sidecar.get(
        "frame_records",
        [],
    )

    if not isinstance(records, list) or not records:
        raise RuntimeError(
            "Sidecar contains no frame_records"
        )

    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(
                "Invalid frame record"
            )

        try:
            brightness_values.append(
                float(record["mean_brightness"])
            )
            delta_values.append(
                float(
                    record[
                        "brightness_delta_adjacent"
                    ]
                )
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise RuntimeError(
                "Frame record is missing valid brightness metrics"
            ) from error

    return (
        np.asarray(
            brightness_values,
            dtype=np.float64,
        ),
        np.asarray(
            delta_values,
            dtype=np.float64,
        ),
    )


def get_trigger_frame_index(
    sidecar: dict[str, Any],
) -> int | None:
    value = sidecar.get(
        "trigger_frame_index"
    )

    if value is None:
        frame_number = sidecar.get(
            "trigger_frame_number"
        )

        if frame_number is not None:
            try:
                return int(frame_number) - 1
            except (
                TypeError,
                ValueError,
            ):
                return None

        return None

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def ensure_destination_folders(
    input_directory: Path,
) -> dict[str, Path]:
    destinations: dict[str, Path] = {}

    for category, folder_name in (
        DESTINATION_FOLDERS.items()
    ):
        destination = (
            input_directory /
            folder_name
        )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        destinations[
            category
        ] = destination

    return destinations


def move_file(
    source: Path,
    destination_directory: Path,
) -> None:
    destination = (
        destination_directory /
        source.name
    )

    if destination.exists():
        raise RuntimeError(
            f"Destination already exists: {destination}"
        )

    shutil.move(
        str(source),
        str(destination),
    )


def move_capture_pair(
    video_path: Path,
    sidecar_path: Path,
    destination_directory: Path,
) -> None:
    # Refuse to start if either destination name already exists so a partial
    # overwrite cannot occur.
    video_destination = (
        destination_directory /
        video_path.name
    )
    sidecar_destination = (
        destination_directory /
        sidecar_path.name
    )

    if video_destination.exists():
        raise RuntimeError(
            f"Destination already exists: {video_destination}"
        )

    if (
        sidecar_path.exists() and
        sidecar_destination.exists()
    ):
        raise RuntimeError(
            f"Destination already exists: {sidecar_destination}"
        )

    move_file(
        video_path,
        destination_directory,
    )

    if sidecar_path.exists():
        try:
            move_file(
                sidecar_path,
                destination_directory,
            )
        except Exception:
            # Put the MP4 back if moving the matching sidecar fails.
            shutil.move(
                str(video_destination),
                str(video_path),
            )
            raise


def classify_capture(
    video_path: Path,
    solution_filter: SolutionFilter,
) -> tuple[str, str]:
    sidecar_path = video_path.with_suffix(
        ".json"
    )

    if not sidecar_path.is_file():
        return (
            "UNCLASSIFIED",
            "Matching JSON sidecar not found",
        )

    try:
        sidecar = read_sidecar(
            sidecar_path
        )

        (
            brightness,
            brightness_delta,
        ) = build_metric_arrays(
            sidecar
        )

        trigger_frame_index = (
            get_trigger_frame_index(
                sidecar
            )
        )

        result = solution_filter.evaluate(
            brightness,
            brightness_delta,
            trigger_frame_index,
        )

        return (
            result.category,
            result.reason,
        )

    except (
        OSError,
        json.JSONDecodeError,
        RuntimeError,
    ) as error:
        return (
            "UNCLASSIFIED",
            str(error),
        )


def move_orphan_sidecars(
    input_directory: Path,
    unclassified_directory: Path,
) -> int:
    moved_count = 0

    for sidecar_path in sorted(
        input_directory.glob("*.json")
    ):
        video_path = sidecar_path.with_suffix(
            ".mp4"
        )

        if video_path.exists():
            continue

        move_file(
            sidecar_path,
            unclassified_directory,
        )

        print(
            f"{sidecar_path.name} -> "
            f"{unclassified_directory.name} "
            "(orphan JSON sidecar)"
        )

        moved_count += 1

    return moved_count


def run_batch(
    input_directory: Path,
) -> int:
    if not input_directory.is_dir():
        raise RuntimeError(
            f"Folder not found: {input_directory}"
        )

    destinations = (
        ensure_destination_folders(
            input_directory
        )
    )

    solution_filter = SolutionFilter()
    counts: Counter[str] = Counter()

    video_files = sorted(
        input_directory.glob("*.mp4")
    )

    for video_path in video_files:
        sidecar_path = video_path.with_suffix(
            ".json"
        )

        category, reason = classify_capture(
            video_path,
            solution_filter,
        )

        destination_directory = (
            destinations[category]
        )

        move_capture_pair(
            video_path,
            sidecar_path,
            destination_directory,
        )

        counts[category] += 1

        print(
            f"{video_path.name} -> "
            f"{destination_directory.name}: "
            f"{reason}"
        )

    orphan_count = move_orphan_sidecars(
        input_directory,
        destinations["UNCLASSIFIED"],
    )

    counts["UNCLASSIFIED"] += orphan_count

    print()
    print("Summary:")
    print(
        f"  True flashes: "
        f"{counts[CATEGORY_TRUE_FLASH]}"
    )
    print(
        f"  Frame dropout anomalies: "
        f"{counts[CATEGORY_FRAME_DROPOUT]}"
    )
    print(
        f"  Bright noise anomalies: "
        f"{counts[CATEGORY_BRIGHT_NOISE]}"
    )
    print(
        f"  Unclassified: "
        f"{counts['UNCLASSIFIED']}"
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify candidate captures and move "
            "MP4/JSON pairs into category subfolders."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing MP4 captures and JSON sidecars",
    )

    arguments = parser.parse_args()

    try:
        return run_batch(
            arguments.folder
        )

    except (
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"Batch classification failed: {error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
