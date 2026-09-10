"""
@file sidecar_writer.py

@brief Transactionally writes the V8 JSON sidecar paired with each saved MP4.

The V8 capture path records camera/capture metadata plus one timing/brightness
record per frame.  It deliberately performs no SolutionFilter replay and no
High/Medium/Low classification.  New captures start as PENDING; the independent
PSF service later applies the frozen logistic classifier and writes FLASH or
ANOMALY plus immutable initial model confidence.
"""

from __future__ import annotations

from pathlib import Path
import json
import os

from common.capture_sidecar import CLASSIFICATION_PENDING
from common.capture_sidecar import SIDECAR_VERSION
from common.capture_sidecar import apply_capture_brightness_summary
from video_capture.camera_reader import CameraFrame
from video_capture.sidecar_analysis import build_sidecar_frame_records


class SidecarWriteError(RuntimeError):
    """Raised when a specific stage of sidecar creation fails."""

    def __init__(
        self,
        stage: str,
        sidecar_path: Path,
        error: Exception,
    ) -> None:
        self.stage = stage
        self.sidecar_path = sidecar_path
        self.temp_path = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        self.original_error = error
        super().__init__(f"{stage} failed for {sidecar_path.name}: {error}")


class SidecarWriter:
    def write_sidecar(
        self,
        frames: list[CameraFrame],
        output_file: str | Path,
        metadata: dict | None = None,
    ) -> dict:
        sidecar_path = Path(output_file).with_suffix(".json")
        temp_path = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")

        try:
            sidecar_data = self._build_sidecar(frames, metadata)
        except Exception as error:
            raise SidecarWriteError("build", sidecar_path, error) from error

        try:
            sidecar_text = json.dumps(sidecar_data, indent=4) + "\n"
            with temp_path.open("w", encoding="utf-8") as file:
                file.write(sidecar_text)
                file.flush()
                os.fsync(file.fileno())
        except Exception as error:
            raise SidecarWriteError("write", sidecar_path, error) from error

        try:
            with temp_path.open("r", encoding="utf-8") as file:
                validated_sidecar = json.load(file)
            if not isinstance(validated_sidecar, dict):
                raise RuntimeError("sidecar root is not a JSON object")
        except Exception as error:
            raise SidecarWriteError("validation", sidecar_path, error) from error

        try:
            temp_path.replace(sidecar_path)
        except Exception as error:
            raise SidecarWriteError("commit", sidecar_path, error) from error

        return sidecar_data

    def _build_sidecar(
        self,
        frames: list[CameraFrame],
        metadata: dict | None = None,
    ) -> dict:
        frame_records = build_sidecar_frame_records(frames)
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

        result["frame_records"] = frame_records

        capture = result.get("capture")
        if not isinstance(capture, dict):
            raise RuntimeError("Sidecar metadata is missing capture")

        capture = dict(capture)
        capture["verified"] = False
        capture["classification"] = CLASSIFICATION_PENDING
        capture["initial_classification"] = None
        capture["type"] = "UK"
        capture["initial_confidence"] = None
        capture["classification_model"] = ""
        capture["description"] = str(capture.get("description", "") or "")
        result["capture"] = capture

        reserved = {
            "sidecar_version",
            "application",
            "capture",
            "camera",
            "candidate",
            "frame_records",
            "frame_count",  # V8 keeps frame_count only under capture.
            "search_bounding_box",
        }
        for key, value in metadata.items():
            if key not in reserved:
                result[key] = value

        apply_capture_brightness_summary(result)
        return result
