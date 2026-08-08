"""
@file sidecar_writer.py

@brief Writes capture metadata and per-frame brightness data to JSON sidecars.
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