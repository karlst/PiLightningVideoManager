"""
@file batch_solution_filter.py

@brief Quickly classify saved Candidate captures using their JSON sidecars.

Each Candidate consists of an MP4 plus its matching JSON sidecar. The Pi has
already run CandidateFinder before saving the clip, so BatchClassifier does
NOT replay CandidateFinder and does NOT decode the MP4.

Instead, BatchClassifier trusts the Candidate trigger recorded by the Pi,
reads the per-frame brightness measurements already stored in the sidecar,
and runs the desktop SolutionFilter over the complete Candidate clip.

This separation is intentional:

    Pi CandidateFinder -> decides which clips are worth saving.
    BatchClassifier    -> decides which saved Candidates are Solutions.

Avoiding MP4 decoding makes normal batch classification very fast even for
large folders. The optional --findCandidates mode deliberately reruns
CandidateFinder using the current CandidateConfig or a one-run --sensitivity
override. Because bright-pixel replay
requires reconstructed pixel-change measurements, that mode decodes each MP4
and is therefore much slower.

By default the classifier moves each MP4/JSON pair into a category subfolder.
For Pi production use, --delete-rejects keeps only true flashes: TRUE_FLASH
pairs are moved into true_flashes and every other classified pair is deleted.
The experimental --copy option remains available for repeated test runs.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
from common.candidate_config import candidate_config_from_settings
from common.candidate_config import load_candidate_settings
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.capture_data import load_capture
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_filter import failed_candidate_result
from video_analyzer.stair_step_decay_filter import CATEGORY_STAIR_STEP_DECAY
from video_analyzer.solution_types import CATEGORY_BRIGHT_NOISE
from video_analyzer.solution_types import CATEGORY_FAILED_CANDIDATE
from video_analyzer.solution_types import CATEGORY_FRAME_DROPOUT
from video_analyzer.solution_types import CATEGORY_STEADY_STATE_CHANGE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH


DESTINATION_FOLDERS = {
    CATEGORY_TRUE_FLASH: "true_flashes",
    CATEGORY_FRAME_DROPOUT: "frame_dropout_anomalies",
    CATEGORY_BRIGHT_NOISE: "bright_noise_anomalies",
    CATEGORY_STEADY_STATE_CHANGE: "steady_state_anomalies",
    CATEGORY_STAIR_STEP_DECAY: "stair_step_decay_anomalies",
    CATEGORY_FAILED_CANDIDATE: "not_candidates",
    "UNCLASSIFIED": "unclassified",
}

# Maximum size of the current PSF activity log before rotation.
PSF_LOG_MAX_BYTES = 10 * 1024

# Prevent the long-running PSF service from writing a START line on every
# periodic run_batch() call. This resets naturally whenever the process restarts.
_psf_start_logged = False


# ## Return the PSF activity-log path beside the captures directory.
def psf_log_path(
    input_directory: Path,
) -> Path:
    return (
        input_directory /
        "logs" /
        "psf.log"
    )


# ## Rotate psf.log to one archive when the next entry would exceed the size limit.
def rotate_psf_log_if_needed(
    log_path: Path,
    additional_bytes: int,
) -> None:
    current_size = 0

    if log_path.exists():
        try:
            current_size = log_path.stat().st_size
        except OSError:
            current_size = 0

    if (
        current_size + additional_bytes
        <= PSF_LOG_MAX_BYTES
    ):
        return

    archive_path = log_path.with_name(
        f"{log_path.name}.archive"
    )

    archive_path.unlink(
        missing_ok=True
    )

    if log_path.exists():
        log_path.replace(
            archive_path
        )


# ## Append one compact UTC-stamped event to the PSF activity log.
def write_psf_log(
    log_path: Path,
    category: str,
    video_name: str = "",
    action: str = "",
    detail: str = "",
) -> None:
    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    fields = [
        timestamp,
        category,
    ]

    if video_name:
        fields.append(
            video_name
        )

    if action:
        fields.append(
            action
        )

    if detail:
        fields.append(
            detail
        )

    line = "  ".join(fields) + "\n"
    additional_bytes = len(
        line.encode("utf-8")
    )

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rotate_psf_log_if_needed(
        log_path,
        additional_bytes,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            line
        )


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


# ## Classify one capture using either the recorded trigger or current Candidate settings.
def classify_capture(
    video_path: Path,
    solution_filter: SolutionFilter,
    candidate_config: CandidateConfig = CANDIDATE_CONFIG,
    find_candidates: bool = False,
    verbosity: int = 0,
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
        # Experimental mode: rerun CandidateFinder using CURRENT CandidateConfig.
        # This is intentionally slower because bright-pixel replay requires
        # decoding the MP4 and reconstructing per-frame pixel-change metrics.
        if find_candidates:
            if verbosity >= 2:
                capture_data = load_capture(
                    video_path
                )
            else:
                with contextlib.redirect_stdout(
                    io.StringIO()
                ):
                    capture_data = load_capture(
                        video_path
                    )

            candidate_result = replay_candidate_finder(
                capture_data,
                candidate_config,
            )

            if candidate_result.frame_index is None:
                result = failed_candidate_result()

                return (
                    result.category,
                    result.reason,
                )

            result = solution_filter.evaluate(
                capture_data.pi_brightness,
                capture_data.pi_brightness_delta,
                candidate_result.frame_index,
                candidate_result.reason,
            )

            return (
                result.category,
                result.reason,
            )

        # Normal fast mode: trust the Candidate trigger already recorded by Pi.
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

        # Preserve the CandidateFinder reason recorded by the Pi so
        # trigger-specific SolutionFilter rules can run in the fast path.
        trigger_reason = ""

        candidate = sidecar.get(
            "candidate"
        )

        if isinstance(candidate, dict):
            trigger_reason = str(
                candidate.get(
                    "trigger_reason",
                    ""
                )
            )
        else:
            # Legacy/reconstructed sidecars may store trigger fields at root.
            trigger_reason = str(
                sidecar.get(
                    "trigger_reason",
                    ""
                )
            )

        result = solution_filter.evaluate(
            brightness,
            brightness_delta,
            trigger_frame_index,
            trigger_reason,
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


# ## Classify every Candidate in one folder and move each pair to its result folder.
def run_batch_solution_filter(
    input_directory: Path,
    verbosity: int = 0,
    copy_only: bool = False,
    delete_rejects: bool = False,
    find_candidates: bool = False,
    candidate_config: CandidateConfig = CANDIDATE_CONFIG,
) -> int:
    if not input_directory.is_dir():
        raise RuntimeError(
            f"Folder not found: {input_directory}"
        )

    if copy_only and delete_rejects:
        raise RuntimeError(
            "--copy and --delete-rejects cannot be used together"
        )

    global _psf_start_logged

    log_path = (
        psf_log_path(input_directory)
        if delete_rejects
        else None
    )

    if (
        delete_rejects
        and log_path is not None
        and not _psf_start_logged
    ):
        write_psf_log(
            log_path,
            "START",
            detail=(
                f"captures={input_directory}"
            ),
        )
        _psf_start_logged = True

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
            candidate_config=candidate_config,
            find_candidates=find_candidates,
            verbosity=verbosity,
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
                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            CATEGORY_TRUE_FLASH,
                            video_path.name,
                            "MOVED",
                        )
                else:
                    delete_capture_pair(
                        video_path,
                        sidecar_path,
                    )
                    if log_path is not None:
                        write_psf_log(
                            log_path,
                            category,
                            video_path.name,
                            "DELETED",
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
            if delete_rejects and log_path is not None:
                write_psf_log(
                    log_path,
                    "ERROR",
                    video_path.name,
                    "SKIPPED",
                    str(error),
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
        f"  Stair-step decay anomalies: "
        f"{counts[CATEGORY_STAIR_STEP_DECAY]}"
    )
    print(
        f"  Not candidates: "
        f"{counts[CATEGORY_FAILED_CANDIDATE]}"
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
            + counts[CATEGORY_STAIR_STEP_DECAY]
            + counts[CATEGORY_FAILED_CANDIDATE]
            + counts["UNCLASSIFIED"]
        )

        print(
            f"  Deleted: {deleted_count}"
        )

    return 0


# ## Build an optional one-run sensitivity override without changing the JSON file.
def build_candidate_config(
    sensitivity: str | None,
) -> CandidateConfig:
    if sensitivity is None:
        return CANDIDATE_CONFIG

    settings = (
        load_candidate_settings()
    )

    settings[
        "sensitivity"
    ] = sensitivity

    return candidate_config_from_settings(
        settings
    )


# ## Always report the effective CandidateFinder settings for this batch run.
def print_candidate_config(
    config: CandidateConfig,
    find_candidates: bool,
) -> None:
    mode_text = (
        "used for CandidateFinder replay"
        if find_candidates
        else "reported only; normal batch trusts sidecar trigger"
    )

    print(
        "CandidateFinder settings "
        f"({mode_text}):"
    )

    print(
        f"  Sensitivity: "
        f"{config.sensitivity}"
    )

    print(
        f"  Brightness delta threshold: "
        f"{config.candidate_brightness_delta_threshold:.3f}"
    )

    print(
        f"  Bright pixel delta threshold: "
        f"{config.candidate_bright_pixel_delta_threshold:.1f}"
    )

    print(
        f"  Bright pixel fraction threshold: "
        f"{config.candidate_bright_pixel_fraction_threshold:.6f}"
    )

    print()


# ## Parse command-line arguments and run BatchClassifier.
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

    parser.add_argument(
        "--findCandidates",
        action="store_true",
        help=(
            "Rerun CandidateFinder using CandidateConfig before "
            "SolutionFilter. This decodes MP4 files and is much slower than "
            "the normal sidecar-only path."
        ),
    )

    parser.add_argument(
        "--sensitivity",
        choices=[
            "high",
            "medium",
            "low",
        ],
        default=None,
        help=(
            "Override CandidateFinder sensitivity for this batch run only. "
            "Does not modify candidate_config.json. "
            "If omitted, use the current shared CandidateConfig."
        ),
    )

    arguments = parser.parse_args()

    try:
        candidate_config = (
            build_candidate_config(
                arguments.sensitivity
            )
        )

        print_candidate_config(
            candidate_config,
            arguments.findCandidates,
        )

        return run_batch(
            arguments.folder,
            verbosity=arguments.verbosity,
            copy_only=arguments.copy,
            delete_rejects=arguments.delete_rejects,
            find_candidates=arguments.findCandidates,
            candidate_config=candidate_config,
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
