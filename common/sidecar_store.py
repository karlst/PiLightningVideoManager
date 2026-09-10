"""Read, validate, and atomically update V8 capture sidecars."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from common.capture_sidecar import CLASSIFICATION_ANOMALY
from common.capture_sidecar import CLASSIFICATION_FLASH
from common.capture_sidecar import SIDECAR_VERSION
from common.capture_sidecar import apply_capture_brightness_summary
from common.classification_model import CLASSIFICATION_MODEL_NAME
from common.classification_model import ClassificationResult


def read_sidecar(sidecar_path: Path) -> dict[str, Any]:
    with sidecar_path.open("r", encoding="utf-8") as file:
        sidecar = json.load(file)

    if not isinstance(sidecar, dict):
        raise RuntimeError("Sidecar root must be a JSON object")

    version = sidecar.get("sidecar_version")
    if version != SIDECAR_VERSION:
        raise RuntimeError(
            f"Sidecar version {version!r} is not supported; convert to V8 first"
        )

    if not isinstance(sidecar.get("capture"), dict):
        raise RuntimeError("V8 sidecar is missing capture metadata")

    return sidecar


def write_sidecar_atomic(sidecar_path: Path, sidecar: dict[str, Any]) -> None:
    """Write and validate JSON before atomically replacing the live sidecar."""
    temporary_path = sidecar_path.with_suffix(".json.tmp")

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            file.write(json.dumps(sidecar, indent=4) + "\n")
            file.flush()
            os.fsync(file.fileno())

        with temporary_path.open("r", encoding="utf-8") as file:
            staged = json.load(file)
        if not isinstance(staged, dict):
            raise RuntimeError("Temporary sidecar root is not a JSON object")

        temporary_path.replace(sidecar_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def update_capture_brightness_summary(sidecar_path: Path) -> None:
    sidecar = read_sidecar(sidecar_path)
    if apply_capture_brightness_summary(sidecar):
        write_sidecar_atomic(sidecar_path, sidecar)


def build_metric_arrays(
    sidecar: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Build classifier input arrays from frame_records already saved by the Pi."""
    records = sidecar.get("frame_records", [])
    if not isinstance(records, list) or not records:
        raise RuntimeError("Sidecar contains no frame_records")

    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Invalid frame record")
        try:
            brightness_values.append(float(record["mean_brightness"]))
            delta_values.append(float(record["brightness_delta_adjacent"]))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "Frame record is missing valid brightness metrics"
            ) from error

    return (
        np.asarray(brightness_values, dtype=np.float64),
        np.asarray(delta_values, dtype=np.float64),
    )


def get_trigger_frame_index(sidecar: dict[str, Any]) -> int | None:
    """Return the Candidate trigger frame recorded by the Pi."""
    candidate = sidecar.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("trigger_frame_index")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        frame_number = candidate.get("trigger_frame_number")
        if frame_number is not None:
            try:
                return int(frame_number) - 1
            except (TypeError, ValueError):
                return None

    value = sidecar.get("trigger_frame_index")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    frame_number = sidecar.get("trigger_frame_number")
    if frame_number is not None:
        try:
            return int(frame_number) - 1
        except (TypeError, ValueError):
            return None

    return None


def apply_classification_result(
    sidecar_path: Path,
    result: ClassificationResult,
) -> None:
    """Persist the initial classifier decision, its confidence, and model identity."""
    sidecar = read_sidecar(sidecar_path)
    capture = sidecar["capture"]

    # Preserve the model's first decision separately from the mutable, current
    # classification used by human review. This function is the production PSF
    # classification write, so both start with the same model result.
    capture["initial_classification"] = result.classification
    capture["classification"] = result.classification
    # The model returns P(FLASH). Store confidence in the class it actually
    # selected so the immutable initial_* provenance reads naturally.
    capture["initial_confidence"] = (
        result.flash_probability
        if result.classification == CLASSIFICATION_FLASH
        else 1.0 - result.flash_probability
    )
    capture["classification_model"] = CLASSIFICATION_MODEL_NAME
    capture["type"] = "UK"

    if result.classification == CLASSIFICATION_FLASH:
        capture["verified"] = False
    elif result.classification == CLASSIFICATION_ANOMALY:
        capture["verified"] = True
    else:
        raise RuntimeError(
            f"Unsupported classifier result: {result.classification}"
        )

    apply_capture_brightness_summary(sidecar)
    write_sidecar_atomic(sidecar_path, sidecar)
