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

from video_capture.camera_reader import CameraFrame
from video_capture.sidecar_analysis import analyze_sidecar_frames


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
        (
            frame_records,
            sensitivity_results,
        ) = analyze_sidecar_frames(
            frames
        )

        result = {
            "sidecar_version": 4
        }

        if metadata is not None:
            result.update(
                metadata
            )

        result[
            "sensitivity_results"
        ] = sensitivity_results

        result[
            "frame_records"
        ] = frame_records

        return result