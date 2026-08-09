"""
@file rebuild_sidecars.py

@brief Reconstruct missing JSON sidecars from saved MP4 capture files.

A normal Pi Camera Capture recording consists of an MP4 video plus a matching
JSON "sidecar". The MP4 contains the encoded video images. The sidecar contains
the information that was known while the Pi was capturing the original raw
frames: frame timing and brightness measurements, trigger information, camera
configuration, application provenance, and the CandidateFinder settings.

If the JSON file has been lost but the MP4 still exists, this utility rebuilds
as much of that sidecar as can reasonably be reconstructed from the encoded
video.

There is an important limitation: an MP4 does not contain everything that was
present in the original live CameraFrame objects or Pi configuration. Exact
camera-frame UTC timestamps, camera location/bearing/FOV, application version,
Pi startup time, and original camera sequence numbers cannot be recovered from
the MP4. Those fields are therefore left blank or null rather than invented.

Brightness and Candidate metrics can be reconstructed by decoding the video.
The utility uses the current shared CandidateFinder, including the bright-pixel
fraction test, so reconstructed Candidate replay uses the same algorithm as the
Pi and desktop Analyzer. The Candidate config stored in a rebuilt sidecar is
the CURRENT config used for reconstruction, not necessarily the config that
existed when the original video was captured.

Rebuilt sidecars use the current nested clip-level organization:

    application
    camera
    capture
    candidate
    frame_records

Existing sidecars are never overwritten by this program.

Command-line behavior:

    RebuildSidecars
        Process MP4 files in the current directory.

    RebuildSidecars <folder>
        Process MP4 files in the specified directory.

    RebuildSidecars <file.mp4>
        Process one MP4 file.

    RebuildSidecars <folder> --recursive
        Also process MP4 files in subdirectories.

For the packaged Windows utility, ffprobe is supplied in the tools directory
beside RebuildSidecars.exe. During source development the shared tool locator
can fall back to an ffprobe installation on PATH.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
from datetime import timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import cv2
import numpy as np

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_finder import CandidateFinder
from video_analyzer.tool_paths import resolve_external_tool


SIDECAR_VERSION = 1
ANALYSIS_VERSION = 3
SIDECAR_SOURCE = "reconstructed_from_video"


# ## Read per-frame presentation times from the MP4 using ffprobe.
def read_frame_times(
    video_path: Path,
) -> list[float]:
    # In the packaged Windows release this resolves to tools\ffprobe.exe
    # beside RebuildSidecars.exe. During source development it may fall back
    # to ffprobe on PATH.
    ffprobe_path = resolve_external_tool(
        "ffprobe"
    )

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time",
        "-of",
        "json",
        str(video_path),
    ]

    creationflags = 0

    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NO_WINDOW
        )

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            creationflags=creationflags,
        )

    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe could not be started"
        ) from None

    except subprocess.CalledProcessError as error:
        message = (
            error.stderr.strip()
            or "ffprobe failed"
        )

        raise RuntimeError(
            message
        ) from error

    try:
        data = json.loads(
            result.stdout
        )

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "ffprobe returned invalid JSON"
        ) from error

    frame_times: list[float] = []

    for frame in data.get(
        "frames",
        [],
    ):
        if not isinstance(
            frame,
            dict,
        ):
            continue

        try:
            frame_times.append(
                float(
                    frame[
                        "best_effort_timestamp_time"
                    ]
                )
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            frame_times.append(
                float("nan")
            )

    return frame_times


# ## Decode the MP4 and reconstruct brightness plus bright-pixel Candidate metrics.
def analyze_video(
    video_path: Path,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    float,
    int,
    int,
]:
    capture = cv2.VideoCapture(
        str(video_path)
    )

    if not capture.isOpened():
        raise RuntimeError(
            f"OpenCV could not open: "
            f"{video_path}"
        )

    nominal_fps = float(
        capture.get(
            cv2.CAP_PROP_FPS
        )
    )

    frame_width_pixels = int(
        capture.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    frame_height_pixels = int(
        capture.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    brightness_values: list[float] = []
    bright_pixel_fraction_values: list[float] = []

    previous_gray_frame: np.ndarray | None = None

    # CandidateFinder defines a bright pixel as one whose grayscale value
    # increased by at least this much from the immediately preceding frame.
    bright_pixel_delta_threshold = float(
        CANDIDATE_CONFIG.
        candidate_bright_pixel_delta_threshold
    )

    while True:
        success, frame = (
            capture.read()
        )

        if not success:
            break

        gray_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        brightness_values.append(
            float(
                gray_frame.mean()
            )
        )

        bright_pixel_fraction = 0.0

        if previous_gray_frame is not None:
            # Convert to signed integers before subtracting so negative pixel
            # changes do not wrap around as unsigned 8-bit values.
            positive_delta = (
                gray_frame.astype(
                    np.int16
                )
                -
                previous_gray_frame.astype(
                    np.int16
                )
            )

            bright_pixel_fraction = float(
                np.count_nonzero(
                    positive_delta >=
                    bright_pixel_delta_threshold
                )
                /
                positive_delta.size
            )

        bright_pixel_fraction_values.append(
            bright_pixel_fraction
        )

        previous_gray_frame = (
            gray_frame
        )

    capture.release()

    if not brightness_values:
        raise RuntimeError(
            f"OpenCV decoded no frames: "
            f"{video_path}"
        )

    brightness = np.asarray(
        brightness_values,
        dtype=np.float64,
    )

    brightness_delta = np.zeros_like(
        brightness
    )

    brightness_delta[1:] = (
        brightness[1:]
        -
        brightness[:-1]
    )

    bright_pixel_fraction = np.asarray(
        bright_pixel_fraction_values,
        dtype=np.float64,
    )

    return (
        brightness,
        brightness_delta,
        bright_pixel_fraction,
        nominal_fps,
        frame_width_pixels,
        frame_height_pixels,
    )


# ## Replay reconstructed metrics through the current shared CandidateFinder.
def reconstruct_trigger(
    brightness: np.ndarray,
    brightness_delta: np.ndarray,
    bright_pixel_fraction: np.ndarray,
) -> tuple[int | None, str]:
    candidate_finder = CandidateFinder(
        CANDIDATE_CONFIG
    )

    for frame_index in range(
        len(brightness)
    ):
        metric = {
            "mean_brightness": float(
                brightness[
                    frame_index
                ]
            ),
            "brightness_delta_adjacent":
                float(
                    brightness_delta[
                        frame_index
                    ]
                ),
            "bright_pixel_fraction":
                float(
                    bright_pixel_fraction[
                        frame_index
                    ]
                ),
        }

        found, reason = (
            candidate_finder.evaluate(
                metric
            )
        )

        if found:
            return (
                frame_index,
                reason,
            )

    return None, ""


# ## Build elapsed milliseconds for each frame using ffprobe timing when possible.
def build_offsets_ms(
    frame_count: int,
    frame_times: list[float],
    nominal_fps: float,
) -> list[float]:
    if len(frame_times) >= frame_count:
        first_time = frame_times[0]

        if np.isfinite(
            first_time
        ):
            offsets: list[float] = []
            valid = True

            for frame_index in range(
                frame_count
            ):
                frame_time = (
                    frame_times[
                        frame_index
                    ]
                )

                if not np.isfinite(
                    frame_time
                ):
                    valid = False
                    break

                offsets.append(
                    round(
                        (
                            frame_time
                            -
                            first_time
                        )
                        *
                        1000.0,
                        3,
                    )
                )

            if valid:
                return offsets

    # If ffprobe timestamps are unavailable, nominal FPS gives a reasonable
    # relative frame spacing. This is reconstructed timing, not Pi timing.
    if nominal_fps <= 0.0:
        nominal_fps = 260.0

    return [
        round(
            (
                frame_index
                /
                nominal_fps
            )
            *
            1000.0,
            3,
        )
        for frame_index
        in range(frame_count)
    ]


# ## Convert CandidateFinder reason text into the stable labels used by sidecars.
def trigger_identity(
    reason: str,
) -> tuple[str, str]:
    reason_lower = (
        reason.lower()
    )

    if "brightness delta" in reason_lower:
        return (
            "brightness_delta",
            "Δ Bright",
        )

    if "brightness trigger" in reason_lower:
        return (
            "brightness",
            "Brightness",
        )

    if "bright pixel trigger" in reason_lower:
        return (
            "bright_pixel_fraction",
            "Bright Pixels",
        )

    if "motion trigger" in reason_lower:
        return (
            "motion",
            "Motion",
        )

    return (
        "unknown",
        "Reconstructed",
    )


# ## Recover the ClipWriter save time when the standard trigger filename contains it.
def saved_utc_from_filename(
    video_path: Path,
) -> str:
    match = re.search(
        r"trigger_(\d{8})T(\d{6})Z",
        video_path.stem,
        flags=re.IGNORECASE,
    )

    if match is None:
        return ""

    try:
        parsed = datetime.strptime(
            (
                match.group(1)
                +
                match.group(2)
            ),
            "%Y%m%d%H%M%S",
        ).replace(
            tzinfo=timezone.utc
        )

    except ValueError:
        return ""

    return parsed.isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z",
    )


# ## Build one current-format reconstructed sidecar dictionary from an MP4.
def build_sidecar(
    video_path: Path,
) -> dict[str, Any]:
    (
        brightness,
        brightness_delta,
        bright_pixel_fraction,
        nominal_fps,
        frame_width_pixels,
        frame_height_pixels,
    ) = analyze_video(
        video_path
    )

    frame_times = read_frame_times(
        video_path
    )

    frame_count = len(
        brightness
    )

    offsets_ms = build_offsets_ms(
        frame_count,
        frame_times,
        nominal_fps,
    )

    (
        trigger_frame_index,
        trigger_reason,
    ) = reconstruct_trigger(
        brightness,
        brightness_delta,
        bright_pixel_fraction,
    )

    (
        trigger_type,
        trigger_display,
    ) = trigger_identity(
        trigger_reason
    )

    frame_records: list[
        dict[str, Any]
    ] = []

    for frame_index in range(
        frame_count
    ):
        frame_records.append(
            {
                "frame_index":
                    frame_index,
                "frame_number":
                    frame_index + 1,

                # These values belonged to the original Pi CameraFrame and
                # cannot be reconstructed from encoded MP4 video.
                "sequence_number":
                    None,
                "timestamp_utc":
                    "",

                "offset_ms":
                    offsets_ms[
                        frame_index
                    ],
                "mean_brightness":
                    round(
                        float(
                            brightness[
                                frame_index
                            ]
                        ),
                        3,
                    ),
                "brightness_delta_adjacent":
                    round(
                        float(
                            brightness_delta[
                                frame_index
                            ]
                        ),
                        3,
                    ),
            }
        )

    trigger_offset_ms = None

    if trigger_frame_index is not None:
        trigger_offset_ms = (
            offsets_ms[
                trigger_frame_index
            ]
        )

    capture_duration_ms = 0.0

    if frame_count > 1:
        capture_duration_ms = round(
            (
                offsets_ms[-1]
                -
                offsets_ms[0]
            ),
            3,
        )

    candidate_config = asdict(
        CANDIDATE_CONFIG
    )

    # Populate what can genuinely be recovered. Original Pi/configuration
    # values that do not exist in the encoded MP4 stay blank or null.
    return {
        "sidecar_version":
            SIDECAR_VERSION,
        "analysis_version":
            ANALYSIS_VERSION,

        "reconstruction": {
            "source":
                SIDECAR_SOURCE,
            "source_video":
                video_path.name,
            "candidate_config_is_current":
                True,
            "note": (
                "Reconstructed from encoded MP4; "
                "unrecoverable original Pi metadata "
                "is blank or null."
            ),
        },

        "application": {
            "name":
                "Pi Camera Capture",
            "version":
                "",
            "start_utc":
                "",
        },

        "camera": {
            "name":
                "",
            "type":
                "",
            "input_format":
                "",
            "frame_width_pixels":
                frame_width_pixels,
            "frame_height_pixels":
                frame_height_pixels,
            "frame_rate_fps":
                nominal_fps,
            "latitude_degrees":
                None,
            "longitude_degrees":
                None,
            "bearing_degrees":
                None,
            "hfov_degrees":
                None,
            "vfov_degrees":
                None,
        },

        "capture": {
            "saved_utc":
                saved_utc_from_filename(
                    video_path
                ),
            "start_utc":
                "",
            "end_utc":
                "",
            "duration_ms":
                capture_duration_ms,
            "frame_count":
                frame_count,
        },

        "candidate": {
            "trigger_type":
                trigger_type,
            "trigger_display":
                trigger_display,
            "trigger_reason":
                trigger_reason,
            "trigger_utc":
                "",
            "trigger_sequence_number":
                None,
            "trigger_frame_index":
                trigger_frame_index,
            "trigger_offset_ms":
                trigger_offset_ms,

            # This is the config used for reconstruction. It may differ from
            # whatever thresholds were active during the original capture.
            "config":
                candidate_config,
        },

        "frame_count":
            frame_count,
        "frame_records":
            frame_records,
    }


# ## Write one reconstructed JSON sidecar next to its matching MP4.
def write_sidecar(
    video_path: Path,
) -> Path:
    sidecar_path = (
        video_path.with_suffix(
            ".json"
        )
    )

    sidecar = build_sidecar(
        video_path
    )

    sidecar_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        )
        +
        "\n",
        encoding="utf-8",
    )

    return sidecar_path


# ## Rebuild one MP4 sidecar or skip it when the matching JSON already exists.
def rebuild_file(
    video_path: Path,
) -> tuple[int, int, int]:
    if not video_path.is_file():
        raise RuntimeError(
            f"File not found: "
            f"{video_path}"
        )

    if video_path.suffix.lower() != ".mp4":
        raise RuntimeError(
            f"Target file must be an MP4: "
            f"{video_path}"
        )

    sidecar_path = (
        video_path.with_suffix(
            ".json"
        )
    )

    if sidecar_path.exists():
        print(
            f"SKIP  "
            f"{video_path.name} "
            f"(sidecar exists)"
        )

        return (
            0,
            1,
            0,
        )

    try:
        print(
            f"BUILD "
            f"{video_path}"
        )

        written_path = write_sidecar(
            video_path
        )

        print(
            f"      -> "
            f"{written_path.name}"
        )

        return (
            1,
            0,
            0,
        )

    except Exception as error:
        print(
            f"FAIL  "
            f"{video_path}: "
            f"{error}"
        )

        return (
            0,
            0,
            1,
        )


# ## Rebuild every missing sidecar in one folder, optionally including subfolders.
def rebuild_folder(
    folder: Path,
    recursive: bool,
) -> tuple[int, int, int]:
    if not folder.is_dir():
        raise RuntimeError(
            f"Folder not found: "
            f"{folder}"
        )

    pattern = (
        "**/*.mp4"
        if recursive
        else "*.mp4"
    )

    video_files = sorted(
        folder.glob(
            pattern
        )
    )

    rebuilt_count = 0
    skipped_count = 0
    failed_count = 0

    for video_path in video_files:
        (
            rebuilt,
            skipped,
            failed,
        ) = rebuild_file(
            video_path
        )

        rebuilt_count += rebuilt
        skipped_count += skipped
        failed_count += failed

    return (
        rebuilt_count,
        skipped_count,
        failed_count,
    )


# ## Parse an optional file/folder target, rebuild requested sidecars, and report results.
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild missing current-format "
            "JSON sidecars from MP4 captures."
        ),
        epilog=(
            "Examples:\n"
            "  RebuildSidecars\n"
            "  RebuildSidecars C:\\Lightning\\Candidates\n"
            "  RebuildSidecars C:\\Lightning\\Candidates\\trigger_001.mp4\n"
            "  RebuildSidecars C:\\Lightning\\Candidates --recursive"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        default=Path("."),
        help=(
            "MP4 file or folder to process. "
            "Defaults to the current directory."
        ),
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "When target is a folder, also process "
            "MP4 files in subfolders"
        ),
    )

    arguments = (
        parser.parse_args()
    )

    try:
        target = arguments.target

        if target.is_file():
            if arguments.recursive:
                parser.error(
                    "--recursive can only be used "
                    "when target is a folder"
                )

            (
                rebuilt_count,
                skipped_count,
                failed_count,
            ) = rebuild_file(
                target
            )

        elif target.is_dir():
            (
                rebuilt_count,
                skipped_count,
                failed_count,
            ) = rebuild_folder(
                target,
                arguments.recursive,
            )

        else:
            raise RuntimeError(
                f"Target not found: "
                f"{target}"
            )

        print()
        print("Summary:")
        print(
            f"  Rebuilt: "
            f"{rebuilt_count}"
        )
        print(
            f"  Existing: "
            f"{skipped_count}"
        )
        print(
            f"  Failed: "
            f"{failed_count}"
        )

        return (
            0
            if failed_count == 0
            else 1
        )

    except (
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"Sidecar rebuild failed: "
            f"{error}"
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
