"""
@file sidecar_writer.py

@brief Writes the JSON sidecar file that accompanies each saved MP4 capture.

A "sidecar" is a separate metadata file that accompanies another file. In this
application, every saved video clip can have two files with the same base name:

    trigger_20260809T120000Z.mp4
    trigger_20260809T120000Z.json

The MP4 contains the actual video images. The JSON sidecar contains information
about that video that either does not belong in the MP4 or is much easier for
our software to read from JSON: capture and camera metadata, trigger
information, application/configuration provenance, and a record for every
frame.

SidecarWriter builds the per-frame portion of that JSON. For each CameraFrame
it records frame numbering and timing, calculates mean image brightness, and
calculates the brightness change from the preceding frame. Additional
clip-level metadata supplied by BufferManager is merged into the same JSON
object before it is written.

Keeping this information in a sidecar makes the MP4/JSON pair a portable
capture record: the video can be played by ordinary video software, while the
desktop analyzer can load the matching JSON file to reconstruct what the Pi
knew about the capture when it was recorded.
"""

from pathlib import Path
import json

import cv2

from video_capture.camera_reader import CameraFrame


class SidecarWriter:

    def write_sidecar(
        self,
        frames: list[CameraFrame],
        output_file: str | Path,
        metadata: dict | None = None
    ) -> dict:
        sidecar_data = self._build_sidecar(
            frames,
            metadata
        )

        sidecar_path = Path(
            output_file
        ).with_suffix(
            ".json"
        )

        sidecar_path.write_text(
            json.dumps(
                sidecar_data,
                indent=4
            ) + "\n",
            encoding="utf-8"
        )

        return sidecar_data

    def _build_sidecar(
        self,
        frames: list[CameraFrame],
        metadata: dict | None = None
    ) -> dict:
        frame_records: list[dict] = []

        previous_mean_brightness: float | None = None
        first_monotonic = 0.0

        if len(frames) > 0:
            first_monotonic = (
                frames[0].timestamp_monotonic
            )

        for frame_index, camera_frame in enumerate(
            frames
        ):
            gray_frame = cv2.cvtColor(
                camera_frame.frame,
                cv2.COLOR_BGR2GRAY
            )

            mean_brightness = float(
                gray_frame.mean()
            )

            brightness_delta_adjacent = 0.0

            if previous_mean_brightness is not None:
                brightness_delta_adjacent = (
                    mean_brightness -
                    previous_mean_brightness
                )

            previous_mean_brightness = mean_brightness

            offset_ms = (
                (
                    camera_frame.timestamp_monotonic -
                    first_monotonic
                ) *
                1000.0
            )

            frame_records.append(
                {
                    "frame_index": frame_index,
                    "sequence_number":
                        camera_frame.sequence_number,
                    "timestamp_utc":
                        camera_frame.timestamp_utc,
                    "offset_ms": round(
                        offset_ms,
                        3
                    ),
                    "mean_brightness": round(
                        mean_brightness,
                        3
                    ),
                    "brightness_delta_adjacent": round(
                        brightness_delta_adjacent,
                        3
                    )
                }
            )

        result = {
            "sidecar_version": 1
        }

        if metadata is not None:
            result.update(
                metadata
            )

        result["frame_records"] = (
            frame_records
        )

        return result