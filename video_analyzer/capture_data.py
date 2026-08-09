"""
@file capture_data.py

@brief Load a saved Candidate capture and prepare the data used by the
desktop video Analyzer.

A Candidate capture normally consists of two files with the same basename:

    trigger_20260809T120000Z.mp4
    trigger_20260809T120000Z.json

The MP4 contains the encoded video. The JSON sidecar contains information
recorded by the Raspberry Pi while the original frames were being captured,
including per-frame brightness measurements and the original trigger.

This module is the Analyzer's main loading layer. It resolves the MP4/JSON
pair, reads encoded-frame metadata with ffprobe, reads the sidecar, and
decodes the MP4 with OpenCV to reconstruct measurements useful during
desktop replay.

In particular, analyze_clip() builds a histogram of positive pixel-brightness
changes for every frame. Keeping the histogram rather than one already-
thresholded value lets the Analyzer experiment with different CandidateFinder
bright-pixel thresholds without decoding the video again.
build_bright_pixel_fraction() converts those histograms into the metric
required by CandidateFinder for the currently selected threshold.

The resulting CaptureData object contains both Pi measurements preserved in
the sidecar and replay measurements reconstructed from the encoded MP4.
Analyzer and candidate-replay code consume CaptureData rather than each
independently reopening and interpreting the capture files.

For a packaged Windows Analyzer, ffprobe is shipped with the application.
tool_paths.resolve_external_tool() finds that bundled copy while still
allowing a normal ffprobe installation to be used during source development.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

import cv2
import numpy as np
import os

from video_analyzer.tool_paths import resolve_external_tool


@dataclass
class CaptureData:
    video_path: Path
    sidecar_path: Path
    frame_info: list[dict[str, Any]]
    sidecar: dict[str, Any] | None
    replay_brightness: np.ndarray
    replay_brightness_delta: np.ndarray
    positive_delta_histograms: np.ndarray
    pi_brightness: np.ndarray
    pi_brightness_delta: np.ndarray
    frame_records: dict[int, dict[str, Any]]
    original_trigger_frame_index: int | None

    @property
    def frame_count(self) -> int:
        return len(self.replay_brightness)

# ## Load one Candidate MP4/sidecar pair and assemble all Analyzer data.
def load_capture(path: Path) -> CaptureData:
    video_path, sidecar_path = resolve_capture_paths(path)

    if not video_path.is_file():
        raise RuntimeError(
            f"Video not found: {video_path}"
        )

    print(f"Video: {video_path}")

    if sidecar_path.is_file():
        print(f"Sidecar: {sidecar_path}")
    else:
        print(
            f"Sidecar not found: {sidecar_path}"
        )

    print("Reading ffprobe metadata...")
    frame_info = read_frame_info(video_path)

    print("Reading sidecar...")
    sidecar = read_sidecar(sidecar_path)

    print("Analyzing clip brightness...")
    (
        replay_brightness,
        replay_brightness_delta,
        positive_delta_histograms,
    ) = analyze_clip(
        video_path
    )

    pi_brightness, pi_brightness_delta = build_pi_metric_arrays(
        sidecar,
        len(replay_brightness),
    )

    frame_records = build_frame_record_map(sidecar)

    original_trigger_frame_index = get_trigger_frame_index(
        sidecar,
        len(replay_brightness),
    )

    print(
        f"Decoded frames: {len(replay_brightness)}"
    )
    print(
        f"ffprobe frames: {len(frame_info)}"
    )

    return CaptureData(
        video_path=video_path,
        sidecar_path=sidecar_path,
        frame_info=frame_info,
        sidecar=sidecar,
        replay_brightness=replay_brightness,
        replay_brightness_delta=replay_brightness_delta,
        positive_delta_histograms=positive_delta_histograms,
        pi_brightness=pi_brightness,
        pi_brightness_delta=pi_brightness_delta,
        frame_records=frame_records,
        original_trigger_frame_index=original_trigger_frame_index,
    )

# ## Resolve a basename, MP4 path, or JSON path into the matching file pair.
def resolve_capture_paths(path: Path) -> tuple[Path, Path]:
    suffix = path.suffix.lower()

    if suffix == ".mp4":
        return path, path.with_suffix(".json")

    if suffix == ".json":
        return path.with_suffix(".mp4"), path

    if suffix == "":
        return path.with_suffix(".mp4"), path.with_suffix(".json")

    raise RuntimeError(
        f"Unsupported capture extension: {path.suffix}"
    )

# ## Read encoded per-frame metadata from the MP4 using ffprobe.
def read_frame_info(filename: Path) -> list[dict[str, Any]]:
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
        "frame=pict_type,key_frame,best_effort_timestamp_time",
        "-of",
        "json",
        str(filename),
    ]

    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            creationflags = creationflags,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe was not found in PATH.") from None
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "ffprobe failed."
        raise RuntimeError(message) from error

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("ffprobe returned invalid JSON.") from error

    frames = data.get("frames", [])

    if not frames:
        raise RuntimeError("ffprobe found no video frames.")

    return frames

# ## Read the JSON sidecar if one exists for this capture.
def read_sidecar(filename: Path) -> dict[str, Any] | None:
    if not filename.is_file():
        return None

    try:
        with filename.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except OSError as error:
        raise RuntimeError(
            f"Unable to read sidecar: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid sidecar JSON: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError("Sidecar JSON must contain an object.")

    return data

# ## Decode the MP4 and reconstruct brightness and positive-delta histograms.
def analyze_clip(
    filename: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    capture = cv2.VideoCapture(str(filename))

    if not capture.isOpened():
        raise RuntimeError(
            f"OpenCV could not open: {filename}"
        )

    brightness_values: list[float] = []
    positive_delta_histograms: list[np.ndarray] = []
    previous_gray: np.ndarray | None = None

    while True:
        success, frame = capture.read()

        if not success:
            break

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        brightness_values.append(
            float(gray.mean())
        )

        if previous_gray is None:
            histogram = np.zeros(
                256,
                dtype=np.int64,
            )
            histogram[0] = gray.size
        else:
            positive_delta = cv2.subtract(
                gray,
                previous_gray,
            )

            histogram = np.bincount(
                positive_delta.ravel(),
                minlength=256,
            ).astype(
                np.int64,
                copy=False,
            )

        positive_delta_histograms.append(
            histogram
        )
        previous_gray = gray

    capture.release()

    if not brightness_values:
        raise RuntimeError("OpenCV decoded no frames.")

    brightness = np.asarray(
        brightness_values,
        dtype=np.float64,
    )

    brightness_delta = np.zeros_like(brightness)
    brightness_delta[1:] = (
        brightness[1:] - brightness[:-1]
    )

    histograms = np.stack(
        positive_delta_histograms,
        axis=0,
    )

    return brightness, brightness_delta, histograms


def build_bright_pixel_fraction(
    positive_delta_histograms: np.ndarray,
    pixel_delta_threshold: float,
) -> np.ndarray:
    """Return fraction of pixels brightening by at least the threshold."""

    if positive_delta_histograms.size == 0:
        return np.asarray([], dtype=np.float64)

    threshold = int(
        np.ceil(
            max(
                0.0,
                min(255.0, float(pixel_delta_threshold)),
            )
        )
    )

    pixel_counts = positive_delta_histograms.sum(
        axis=1
    ).astype(
        np.float64
    )

    bright_counts = positive_delta_histograms[
        :,
        threshold:
    ].sum(
        axis=1
    ).astype(
        np.float64
    )

    fractions = np.zeros_like(
        pixel_counts,
        dtype=np.float64,
    )

    np.divide(
        bright_counts,
        pixel_counts,
        out=fractions,
        where=pixel_counts > 0.0,
    )

    return fractions

# ## Build frame-aligned arrays from brightness metrics recorded by the Pi.
def build_pi_metric_arrays(
    sidecar: dict[str, Any] | None,
    frame_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    pi_brightness = np.full(
        frame_count,
        np.nan,
        dtype=np.float64,
    )
    pi_brightness_delta = np.full(
        frame_count,
        np.nan,
        dtype=np.float64,
    )

    if sidecar is None:
        return pi_brightness, pi_brightness_delta

    records = sidecar.get("frame_records", [])

    if not isinstance(records, list):
        return pi_brightness, pi_brightness_delta

    for list_index, record in enumerate(records):
        if not isinstance(record, dict):
            continue

        try:
            frame_index = int(
                record.get("frame_index", list_index)
            )
        except (TypeError, ValueError):
            continue

        if not 0 <= frame_index < frame_count:
            continue

        try:
            pi_brightness[frame_index] = float(
                record["mean_brightness"]
            )
        except (KeyError, TypeError, ValueError):
            pass

        try:
            pi_brightness_delta[frame_index] = float(
                record["brightness_delta_adjacent"]
            )
        except (KeyError, TypeError, ValueError):
            pass

    return pi_brightness, pi_brightness_delta

# ## Index sidecar frame records by frame index for quick Analyzer lookup.
def build_frame_record_map(
    sidecar: dict[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}

    if sidecar is None:
        return records

    raw_records = sidecar.get(
        "frame_records",
        [],
    )

    if not isinstance(raw_records, list):
        return records

    for list_index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            continue

        raw_frame_index = record.get(
            "frame_index",
            list_index,
        )

        try:
            frame_index = int(raw_frame_index)
        except (TypeError, ValueError):
            continue

        records[frame_index] = record

    return records

# ## Read a current nested sidecar field with fallback to an older flat field.
def get_sidecar_value(
    sidecar: dict[str, Any] | None,
    section_name: str,
    key: str,
    legacy_key: str | None = None,
    default: Any = None,
) -> Any:
    """
    Sidecar format compatibility helper.

    Current sidecars group clip-level fields under sections such as "capture"
    and "candidate". Older sidecars stored many of those fields at the top
    level. Prefer the current nested field, but fall back to the older flat
    field so Analyzer can continue to open archived captures.
    """
    if sidecar is None:
        return default

    section = sidecar.get(
        section_name
    )

    if isinstance(
        section,
        dict,
    ) and key in section:
        return section.get(
            key,
            default,
        )

    fallback_key = (
        legacy_key
        if legacy_key is not None
        else key
    )

    return sidecar.get(
        fallback_key,
        default,
    )


# ## Recover and validate the original Candidate trigger frame from the sidecar.
def get_trigger_frame_index(
    sidecar: dict[str, Any] | None,
    frame_count: int,
) -> int | None:
    if sidecar is None:
        return None

    value = get_sidecar_value(
        sidecar,
        "candidate",
        "trigger_frame_index",
        "trigger_frame_index",
    )

    if value is None:
        frame_number = get_sidecar_value(
            sidecar,
            "candidate",
            "trigger_frame_number",
            "trigger_frame_number",
        )

        if frame_number is not None:
            try:
                value = int(frame_number) - 1
            except (TypeError, ValueError):
                value = None

    if value is None:
        return None

    try:
        frame_index = int(value)
    except (TypeError, ValueError):
        return None

    if 0 <= frame_index < frame_count:
        return frame_index

    return None
