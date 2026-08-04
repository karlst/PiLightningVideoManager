"""Rebuild missing JSON sidecars from MP4 files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import cv2
import numpy as np

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_finder import CandidateFinder


SIDECAR_SOURCE = "reconstructed_from_video"
ANALYSIS_VERSION = 3


def read_frame_times(video_path: Path) -> list[float]:
    command = [
        "ffprobe",
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
        creationflags = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe was not found in PATH") from None
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "ffprobe failed"
        raise RuntimeError(message) from error

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("ffprobe returned invalid JSON") from error

    frame_times: list[float] = []

    for frame in data.get("frames", []):
        if not isinstance(frame, dict):
            continue

        try:
            frame_times.append(
                float(frame["best_effort_timestamp_time"])
            )
        except (KeyError, TypeError, ValueError):
            frame_times.append(float("nan"))

    return frame_times


def analyze_video(
    video_path: Path,
) -> tuple[np.ndarray, np.ndarray, float]:
    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise RuntimeError(
            f"OpenCV could not open: {video_path}"
        )

    nominal_fps = float(
        capture.get(cv2.CAP_PROP_FPS)
    )

    brightness_values: list[float] = []

    while True:
        success, frame = capture.read()

        if not success:
            break

        gray_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        brightness_values.append(
            float(gray_frame.mean())
        )

    capture.release()

    if not brightness_values:
        raise RuntimeError(
            f"OpenCV decoded no frames: {video_path}"
        )

    brightness = np.asarray(
        brightness_values,
        dtype=np.float64,
    )

    brightness_delta = np.zeros_like(
        brightness
    )

    brightness_delta[1:] = (
        brightness[1:] -
        brightness[:-1]
    )

    return (
        brightness,
        brightness_delta,
        nominal_fps,
    )


def reconstruct_trigger(
    brightness: np.ndarray,
    brightness_delta: np.ndarray,
) -> tuple[int | None, str]:
    candidate_finder = CandidateFinder(
        CANDIDATE_CONFIG
    )

    for frame_index in range(len(brightness)):
        metric = {
            "mean_brightness": float(
                brightness[frame_index]
            ),
            "brightness_delta_adjacent": float(
                brightness_delta[frame_index]
            ),
            "changed_pixel_fraction": 0.0,
        }

        found, reason = candidate_finder.evaluate(
            metric
        )

        if found:
            return frame_index, reason

    return None, ""


def build_offsets_ms(
    frame_count: int,
    frame_times: list[float],
    nominal_fps: float,
) -> list[float]:
    if len(frame_times) >= frame_count:
        first_time = frame_times[0]

        if np.isfinite(first_time):
            offsets: list[float] = []
            valid = True

            for frame_index in range(frame_count):
                frame_time = frame_times[frame_index]

                if not np.isfinite(frame_time):
                    valid = False
                    break

                offsets.append(
                    round(
                        (
                            frame_time -
                            first_time
                        ) *
                        1000.0,
                        3,
                    )
                )

            if valid:
                return offsets

    if nominal_fps <= 0.0:
        nominal_fps = 260.0

    return [
        round(
            (
                frame_index /
                nominal_fps
            ) *
            1000.0,
            3,
        )
        for frame_index in range(frame_count)
    ]


def trigger_identity(
    reason: str,
) -> tuple[str, str]:
    reason_lower = reason.lower()

    if "brightness delta" in reason_lower:
        return "brightness_delta", "Δ Bright"

    if "brightness trigger" in reason_lower:
        return "brightness", "Brightness"

    if "motion trigger" in reason_lower:
        return "motion", "Motion"

    return "unknown", "Reconstructed"


def build_sidecar(
    video_path: Path,
) -> dict[str, Any]:
    (
        brightness,
        brightness_delta,
        nominal_fps,
    ) = analyze_video(video_path)

    frame_times = read_frame_times(
        video_path
    )

    frame_count = len(brightness)

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
    )

    (
        trigger_type,
        trigger_display,
    ) = trigger_identity(
        trigger_reason
    )

    frame_records: list[dict[str, Any]] = []

    for frame_index in range(frame_count):
        frame_records.append(
            {
                "frame_index": frame_index,
                "frame_number": frame_index + 1,
                "sequence_number": None,
                "timestamp_utc": "",
                "offset_ms": offsets_ms[frame_index],
                "mean_brightness": round(
                    float(brightness[frame_index]),
                    3,
                ),
                "brightness_delta_adjacent": round(
                    float(
                        brightness_delta[
                            frame_index
                        ]
                    ),
                    3,
                ),
            }
        )

    trigger_frame_number = None
    trigger_offset_ms = None

    if trigger_frame_index is not None:
        trigger_frame_number = (
            trigger_frame_index + 1
        )
        trigger_offset_ms = (
            offsets_ms[
                trigger_frame_index
            ]
        )

    capture_duration_ms = 0.0

    if frame_count > 1:
        capture_duration_ms = (
            offsets_ms[-1] -
            offsets_ms[0]
        )

    return {
        "analysis_version": ANALYSIS_VERSION,
        "sidecar_source": SIDECAR_SOURCE,
        "source_video": video_path.name,
        "frame_count": frame_count,
        "capture_start_utc": "",
        "capture_end_utc": "",
        "capture_duration_ms": round(
            capture_duration_ms,
            3,
        ),
        "trigger_type": trigger_type,
        "trigger_display": trigger_display,
        "trigger_reason": trigger_reason,
        "trigger_utc": "",
        "trigger_sequence_number": None,
        "trigger_frame_index": trigger_frame_index,
        "trigger_frame_number": trigger_frame_number,
        "trigger_offset_ms": trigger_offset_ms,
        "frame_records": frame_records,
    }


def write_sidecar(
    video_path: Path,
) -> Path:
    sidecar_path = video_path.with_suffix(
        ".json"
    )

    sidecar = build_sidecar(
        video_path
    )

    sidecar_path.write_text(
        json.dumps(
            sidecar,
            indent=4,
        ) + "\n",
        encoding="utf-8",
    )

    return sidecar_path


def rebuild_folder(
    folder: Path,
    recursive: bool,
) -> tuple[int, int, int]:
    if not folder.is_dir():
        raise RuntimeError(
            f"Folder not found: {folder}"
        )

    pattern = (
        "**/*.mp4"
        if recursive
        else "*.mp4"
    )

    video_files = sorted(
        folder.glob(pattern)
    )

    rebuilt_count = 0
    skipped_count = 0
    failed_count = 0

    for video_path in video_files:
        sidecar_path = (
            video_path.with_suffix(
                ".json"
            )
        )

        if sidecar_path.exists():
            print(
                f"SKIP  {video_path.name} "
                "(sidecar exists)"
            )
            skipped_count += 1
            continue

        try:
            print(
                f"BUILD {video_path}"
            )

            written_path = write_sidecar(
                video_path
            )

            print(
                f"      -> {written_path.name}"
            )

            rebuilt_count += 1

        except Exception as error:
            print(
                f"FAIL  {video_path}: {error}"
            )
            failed_count += 1

    return (
        rebuilt_count,
        skipped_count,
        failed_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild missing JSON sidecars "
            "from MP4 captures."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing MP4 captures",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help=(
            "Also process MP4 files in subfolders"
        ),
    )

    arguments = parser.parse_args()

    try:
        (
            rebuilt_count,
            skipped_count,
            failed_count,
        ) = rebuild_folder(
            arguments.folder,
            arguments.recursive,
        )

        print()
        print("Summary:")
        print(f"  Rebuilt: {rebuilt_count}")
        print(f"  Existing: {skipped_count}")
        print(f"  Failed: {failed_count}")

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
            f"Sidecar rebuild failed: {error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
