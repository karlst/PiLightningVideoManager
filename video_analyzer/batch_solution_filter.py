"""
@file batch_solution_filter.py

@brief Quickly classify saved Candidate captures using their JSON sidecars.

Each Candidate consists of an MP4 plus its matching JSON sidecar. The Pi has
already run CandidateFinder before saving the clip, so BatchSolutionFilter does
NOT replay CandidateFinder and does NOT decode the MP4.

Instead, BatchSolutionFilter trusts the Candidate trigger recorded by the Pi,
reads the per-frame brightness measurements already stored in the sidecar,
and runs the SolutionFilter over the complete Candidate clip.

This separation is intentional:

    Pi CandidateFinder -> decides which clips are worth saving.
    BatchSolutionFilter    -> decides which saved Candidates are Solutions.

Avoiding MP4 decoding makes batch filtering very fast even for large
folders.

By default the classifier moves each MP4/JSON pair into a category subfolder.
For Pi production use, --delete-rejects keeps only true flashes: TRUE_FLASH
pairs are moved into true_flashes and every other classified pair is deleted.
The experimental --copy option remains available for repeated test runs.
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


# ## Read and validate one JSON sidecar.
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


# ## Build SolutionFilter input arrays from brightness data already saved by the Pi.
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


# ## Return the Candidate trigger frame recorded by the Pi.
def get_trigger_frame_index(
    sidecar: dict[str, Any],
) -> int | None:
    # Current sidecars store Candidate information in a nested object.
    candidate = sidecar.get(
        "candidate"
    )

    if isinstance(candidate, dict):
        value = candidate.get(
            "trigger_frame_index"
        )

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        frame_number = candidate.get(
            "trigger_frame_number"
        )

        if frame_number is not None:
            try:
                return int(frame_number) - 1
            except (TypeError, ValueError):
                return None

    # Legacy/reconstructed sidecars may store trigger fields at the root.
    value = sidecar.get(
        "trigger_frame_index"
    )

    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    frame_number = sidecar.get(
        "trigger_frame_number"
    )

    if frame_number is not None:
        try:
            return int(frame_number) - 1
        except (TypeError, ValueError):
            return None

    return None


# ## Create all category destination folders and return their paths.
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


# ## Move one file without ever overwriting an existing destination file.
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


# ## Delete an MP4 and its matching sidecar without touching unrelated files.
def delete_capture_pair(
    video_path: Path,
    sidecar_path: Path,
) -> None:
    video_path.unlink(
        missing_ok=True
    )

    sidecar_path.unlink(
        missing_ok=True
    )


# ## Move an MP4 and matching sidecar together, rolling back if the second move fails.
def move_capture_pair(
    video_path: Path,
    sidecar_path: Path,
    destination_directory: Path,
    copy_only: bool = False,
) -> None:
    video_destination = destination_directory / video_path.name
    sidecar_destination = destination_directory / sidecar_path.name

    if video_destination.exists():
        raise RuntimeError(
            f"Destination already exists: {video_destination}"
        )

    if sidecar_path.exists() and sidecar_destination.exists():
        raise RuntimeError(
            f"Destination already exists: {sidecar_destination}"
        )

    if copy_only:
        shutil.copy2(
            video_path,
            video_destination,
        )

        if sidecar_path.exists():
            try:
                shutil.copy2(
                    sidecar_path,
                    sidecar_destination,
                )
            except Exception:
                video_destination.unlink(missing_ok=True)
                raise

        return

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
            shutil.move(
                str(video_destination),
                str(video_path),
            )
            raise


# ## Classify one saved Candidate using only its sidecar and recorded trigger.
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

        if trigger_frame_index is None:
            return (
                "UNCLASSIFIED",
                "Sidecar contains no valid Candidate trigger frame",
            )

        if not 0 <= trigger_frame_index < len(brightness):
            return (
                "UNCLASSIFIED",
                "Candidate trigger frame is outside frame_records",
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


# ## Move JSON files that have no matching MP4 into the unclassified folder.
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


# ## Classify every Candidate in one folder and move each pair to its result folder (unless delete_rejects).
def run_batch_solution_filter(
    input_directory: Path,
    verbosity: int = 0,
    copy_only: bool = False,
    delete_rejects: bool = False,
) -> int:
    if not input_directory.is_dir():
        raise RuntimeError(
            f"Folder not found: {input_directory}"
        )

    if copy_only and delete_rejects:
        raise RuntimeError(
            "--copy and --delete-rejects cannot be used together"
        )

    if delete_rejects:
        true_flash_directory = (
            input_directory /
            DESTINATION_FOLDERS[
                CATEGORY_TRUE_FLASH
            ]
        )

        true_flash_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        destinations = {
            CATEGORY_TRUE_FLASH:
                true_flash_directory
        }
    else:
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

        try:
            if delete_rejects:
                if category == CATEGORY_TRUE_FLASH:
                    move_capture_pair(
                        video_path,
                        sidecar_path,
                        destinations[
                            CATEGORY_TRUE_FLASH
                        ],
                    )
                else:
                    delete_capture_pair(
                        video_path,
                        sidecar_path,
                    )
            else:
                destination_directory = (
                    destinations[category]
                )

                move_capture_pair(
                    video_path,
                    sidecar_path,
                    destination_directory,
                    copy_only=copy_only,
                )

        except RuntimeError as error:
            print(
                f"SKIP  {video_path.name}: "
                f"{error}"
            )
            continue

        counts[category] += 1

        if verbosity >= 1:
            if delete_rejects:
                action = (
                    "-> true_flashes"
                    if category == CATEGORY_TRUE_FLASH
                    else "-> DELETED"
                )
                print(
                    f"{video_path.name} "
                    f"{action}: {reason}"
                )
            else:
                print(
                    f"{video_path.name} -> "
                    f"{destination_directory.name}: "
                    f"{reason}"
                )

    orphan_count = 0

    if not copy_only and not delete_rejects:
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
        f"  Steady-state anomalies: "
        f"{counts[CATEGORY_STEADY_STATE_CHANGE]}"
    )
    print(
        f"  Unclassified: "
        f"{counts['UNCLASSIFIED']}"
    )

    if delete_rejects:
        deleted_count = (
            counts[CATEGORY_FRAME_DROPOUT]
            + counts[CATEGORY_BRIGHT_NOISE]
            + counts[CATEGORY_STEADY_STATE_CHANGE]
            + counts["UNCLASSIFIED"]
        )

        print(
            f"  Deleted: {deleted_count}"
        )

    return 0


# ## Parse command-line arguments and run BatchSolutionFilter.
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify saved Candidate captures using "
            "sidecar brightness data and SolutionFilter."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing MP4 captures and JSON sidecars",
    )

    parser.add_argument(
        "-v",
        "--verbosity",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help=(
            "Verbosity: 0=quiet (default), "
            "1=one line per capture, "
            "2=reserved for detailed diagnostics"
        ),
    )

    parser.add_argument(
        "--copy",
        action="store_true",
        help=(
            "Copy classified MP4/JSON pairs instead of moving them. "
            "Useful for repeated experimental runs."
        ),
    )

    parser.add_argument(
        "--delete-rejects",
        action="store_true",
        help=(
            "Pi production mode: move TRUE_FLASH pairs to "
            "true_flashes and delete all other classified pairs."
        ),
    )

    arguments = parser.parse_args()

    try:
        return run_batch_solution_filter(
            arguments.folder,
            verbosity=arguments.verbosity,
            copy_only=arguments.copy,
            delete_rejects=arguments.delete_rejects,
        )

    except (
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"Batch solution filter failed: {error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
