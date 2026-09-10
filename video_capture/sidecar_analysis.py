"""
@file sidecar_analysis.py

@brief Builds per-frame brightness records for a capture sidecar.

V8 sidecars no longer run the legacy SolutionFilter or generate High/Medium/Low
classification signatures while the capture is being written.  This module now
has one production responsibility: convert captured CameraFrame objects into the
brightness/timing records required by the frozen logistic classifier and by the
Capture Editor.
"""

from __future__ import annotations

import cv2

from video_capture.camera_reader import CameraFrame


def build_sidecar_frame_records(frames: list[CameraFrame]) -> list[dict]:
    """Build the V8 per-frame timing and brightness records."""
    frame_records: list[dict] = []
    previous_mean_brightness: float | None = None
    first_monotonic = frames[0].timestamp_monotonic if frames else 0.0

    for frame_index, camera_frame in enumerate(frames):
        gray_frame = cv2.cvtColor(camera_frame.frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(gray_frame.mean())

        brightness_delta_adjacent = 0.0
        if previous_mean_brightness is not None:
            brightness_delta_adjacent = mean_brightness - previous_mean_brightness

        offset_ms = (
            (camera_frame.timestamp_monotonic - first_monotonic) * 1000.0
        )

        frame_records.append(
            {
                "frame_index": frame_index,
                "timestamp_utc": camera_frame.timestamp_utc,
                "offset_ms": round(offset_ms, 3),
                "mean_brightness": round(mean_brightness, 3),
                "brightness_delta_adjacent": round(
                    brightness_delta_adjacent,
                    3,
                ),
            }
        )

        previous_mean_brightness = mean_brightness

    return frame_records
