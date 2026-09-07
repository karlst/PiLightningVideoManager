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

from common.capture_sidecar import SIDECAR_VERSION, apply_capture_brightness_summary
from video_capture.camera_reader import CameraFrame
from video_capture.sidecar_analysis import analyze_sidecar_frames


_SOLUTION_CATEGORY_TO_CODE = {
    "TRUE_FLASH": "TF",
    "BRIGHT_NOISE": "NA",
    "BRIGHT_NOISE_ANOMALY": "NA",
    "NOISE_ANOMALY": "NA",
    "STAIR_STEP_DECAY": "STA",
    "STAIRSTEP_ANOMALY": "STA",
    "STAIR_STEP_ANOMALY": "STA",
    "SST": "STA",
    "STEADY_STATE_CHANGE": "SSA",
    "STEADY_STATE_ANOMALY": "SSA",
    "FRAME_DROPOUT": "FDA",
    "FRAME_DROPOUT_ANOMALY": "FDA",
    "FAILED_CANDIDATE": "NAC",
    "NO_CANDIDATE": "NAC",
    "NOT_A_CANDIDATE": "NAC",
}


def _build_hml_classification(
    sensitivity_results: dict,
) -> str:
    codes: list[str] = []

    for sensitivity in (
        "high",
        "medium",
        "low",
    ):
        result = sensitivity_results.get(
            sensitivity,
            {},
        )

        category = str(
            result.get(
                "solution_category",
                "",
            ) or ""
        ).strip().upper()

        codes.append(
            _SOLUTION_CATEGORY_TO_CODE.get(
                category,
                "UNK",
            )
        )

    return "-".join(
        codes
    )


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
        frame_records, sensitivity_results = analyze_sidecar_frames(frames)

        metadata = dict(metadata or {})
        result: dict = {"sidecar_version": SIDECAR_VERSION}

        for name in ("application", "capture", "camera", "candidate"):
            if name in metadata:
                result[name] = metadata[name]

        camera = result.get("camera")
        if isinstance(camera, dict):
            camera = dict(camera)
            box = camera.get("search_bounding_box")
            if isinstance(box, dict):
                if all(k in box for k in ("range", "lat", "lon")):
                    camera["search_bounding_box"] = {
                        "range": list(box["range"]),
                        "lat": list(box["lat"]),
                        "lon": list(box["lon"]),
                    }
                else:
                    required = (
                        "minimum_range_miles",
                        "maximum_range_miles",
                        "min_latitude_degrees",
                        "max_latitude_degrees",
                        "min_longitude_degrees",
                        "max_longitude_degrees",
                    )
                    if all(k in box for k in required):
                        camera["search_bounding_box"] = {
                            "range": [
                                box["minimum_range_miles"],
                                box["maximum_range_miles"],
                            ],
                            "lat": [
                                box["min_latitude_degrees"],
                                box["max_latitude_degrees"],
                            ],
                            "lon": [
                                box["min_longitude_degrees"],
                                box["max_longitude_degrees"],
                            ],
                        }
            result["camera"] = camera

        result["sensitivity_results"] = sensitivity_results
        result["frame_records"] = frame_records

        capture = result.get(
            "capture"
        )

        if not isinstance(
            capture,
            dict,
        ):
            raise RuntimeError(
                "Sidecar metadata is missing capture"
            )

        capture = dict(
            capture
        )

        capture[
            "verified"
        ] = False
        capture[
            "classification"
        ] = _build_hml_classification(
            sensitivity_results
        )
        capture[
            "type"
        ] = "UK"
        capture[
            "description"
        ] = str(
            capture.get(
                "description",
                "",
            ) or ""
        )

        result[
            "capture"
        ] = capture

        reserved = {
            "sidecar_version", "application", "capture", "camera", "candidate",
            "sensitivity_results", "frame_records", "search_bounding_box",
        }
        for key, value in metadata.items():
            if key not in reserved:
                result[key] = value

        apply_capture_brightness_summary(result)
        return result
