"""Current Pi Camera V8 sidecar schema helpers."""

from __future__ import annotations

import copy
import math
from typing import Any

SIDECAR_VERSION = 8

CLASSIFICATION_PENDING = "PENDING"
CLASSIFICATION_FLASH = "FLASH"
CLASSIFICATION_ANOMALY = "ANOMALY"

CLASSIFICATION_CODE_TO_NAME = {
    CLASSIFICATION_PENDING: "Pending",
    CLASSIFICATION_FLASH: "Flash",
    CLASSIFICATION_ANOMALY: "Anomaly",
}

CLASSIFICATION_NAME_TO_CODE = {
    name: code
    for code, name in CLASSIFICATION_CODE_TO_NAME.items()
}

CLASSIFICATION_CODES = tuple(CLASSIFICATION_CODE_TO_NAME)

LIGHTNING_TYPES = (
    "UK",
    "CG",
    "IC",
    "LCC",
)


def normalize_classification(value: Any) -> str:
    """Normalize one V8 classification token."""
    text = str(value or "").strip()
    upper = text.upper()

    if upper in CLASSIFICATION_CODES:
        return upper

    if text in CLASSIFICATION_NAME_TO_CODE:
        return CLASSIFICATION_NAME_TO_CODE[text]

    raise RuntimeError(f"Unknown V8 classification: {text or '<blank>'}")


def capture_brightness_summary(
    sidecar: dict[str, Any],
) -> tuple[float, float]:
    """Return (max positive adjacent delta, mean frame brightness), 1 decimal."""
    records = sidecar.get("frame_records", [])
    if not isinstance(records, list) or not records:
        raise RuntimeError("Sidecar contains no frame_records")

    brightness_values: list[float] = []
    delta_values: list[float] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            brightness = float(record["mean_brightness"])
            delta = float(record["brightness_delta_adjacent"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(brightness):
            brightness_values.append(brightness)
        if math.isfinite(delta):
            delta_values.append(delta)

    if not brightness_values:
        raise RuntimeError("frame_records contain no valid mean_brightness values")
    if not delta_values:
        raise RuntimeError(
            "frame_records contain no valid brightness_delta_adjacent values"
        )

    max_positive_delta = max(0.0, max(delta_values))
    mean_brightness = sum(brightness_values) / len(brightness_values)

    return round(max_positive_delta, 1), round(mean_brightness, 1)


def apply_capture_brightness_summary(sidecar: dict[str, Any]) -> bool:
    capture = sidecar.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("Sidecar is missing capture metadata")

    max_delta, mean_brightness = capture_brightness_summary(sidecar)
    changed = (
        capture.get("max_brightness_delta") != max_delta
        or capture.get("mean_brightness") != mean_brightness
    )
    capture["max_brightness_delta"] = max_delta
    capture["mean_brightness"] = mean_brightness
    return changed


def normalize_sidecar(
    sidecar: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Normalize a current V8 sidecar without migrating older schemas.

    V8 workflow fields live inside ``capture``:

        capture.verified
        capture.classification       current authoritative PENDING / FLASH / ANOMALY
        capture.initial_classification original model FLASH / ANOMALY, or null pre-PSF
        capture.type                 UK / CG / IC / LCC
        capture.initial_confidence   confidence of initial_classification, or null pre-PSF
        capture.classification_model model identifier, or blank pre-PSF
        capture.description

    Older sidecars must be converted before use with the V8 production path.
    """
    if not isinstance(sidecar, dict):
        raise TypeError("sidecar must be a dictionary")

    version = sidecar.get("sidecar_version")
    if version != SIDECAR_VERSION:
        raise RuntimeError(
            f"Sidecar version {version!r} is not supported; "
            "convert the capture to V8 first"
        )

    capture = sidecar.get("capture")
    if not isinstance(capture, dict):
        raise RuntimeError("V8 sidecar is missing capture metadata")

    normalized = copy.deepcopy(sidecar)

    # V8 has one authoritative frame count: capture.frame_count.
    # Remove the legacy duplicate if an early V8 file contains it.
    normalized.pop("frame_count", None)

    normalized_capture = normalized["capture"]

    verified = normalized_capture.get("verified")
    if not isinstance(verified, bool):
        raise RuntimeError("capture.verified must be boolean")

    classification = normalize_classification(
        normalized_capture.get("classification")
    )

    initial_value = normalized_capture.get("initial_classification")
    initial_classification: str | None
    if initial_value in (None, ""):
        initial_classification = None
    else:
        initial_classification = normalize_classification(initial_value)
        if initial_classification == CLASSIFICATION_PENDING:
            raise RuntimeError("capture.initial_classification cannot be PENDING")

    lightning_type = str(
        normalized_capture.get("type", "UK") or "UK"
    ).strip().upper()
    if lightning_type not in LIGHTNING_TYPES:
        raise RuntimeError(f"Unknown lightning type: {lightning_type}")

    initial_confidence_value = normalized_capture.get("initial_confidence")
    initial_confidence: float | None
    if initial_confidence_value is None:
        initial_confidence = None
    else:
        try:
            initial_confidence = float(initial_confidence_value)
        except (TypeError, ValueError) as error:
            raise RuntimeError("capture.initial_confidence must be numeric or null") from error
        if not math.isfinite(initial_confidence) or not 0.0 <= initial_confidence <= 1.0:
            raise RuntimeError("capture.initial_confidence must be between 0 and 1")

    classification_model = str(
        normalized_capture.get("classification_model", "") or ""
    ).strip()

    if classification == CLASSIFICATION_PENDING:
        if verified:
            raise RuntimeError("PENDING capture cannot be verified")
        if initial_classification is not None:
            raise RuntimeError("PENDING capture must have null initial_classification")
        if initial_confidence is not None:
            raise RuntimeError("PENDING capture must have null initial_confidence")
        if classification_model:
            raise RuntimeError("PENDING capture must not name a classification model")
    else:
        # Model provenance is an all-or-nothing triplet. Historical/manual V8
        # records may omit all three, but when present they stay immutable even
        # if a human later changes capture.classification.
        model_fields_present = (
            initial_classification is not None,
            initial_confidence is not None,
            bool(classification_model),
        )
        if any(model_fields_present) and not all(model_fields_present):
            raise RuntimeError(
                "capture.initial_classification, capture.initial_confidence and "
                "capture.classification_model must all be present or all be absent"
            )

    if classification == CLASSIFICATION_ANOMALY and not verified:
        raise RuntimeError("ANOMALY capture must be verified")

    description = str(normalized_capture.get("description", "") or "")

    try:
        max_brightness_delta = round(
            float(normalized_capture["max_brightness_delta"]),
            1,
        )
        mean_brightness = round(
            float(normalized_capture["mean_brightness"]),
            1,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "V8 capture must contain numeric max_brightness_delta and mean_brightness"
        ) from error

    if not (
        math.isfinite(max_brightness_delta)
        and math.isfinite(mean_brightness)
    ):
        raise RuntimeError("V8 capture brightness summary values must be finite")

    if max_brightness_delta < 0.0:
        raise RuntimeError("capture.max_brightness_delta must be non-negative")

    normalized_capture["verified"] = verified
    normalized_capture["classification"] = classification
    normalized_capture["initial_classification"] = initial_classification
    normalized_capture["type"] = lightning_type
    normalized_capture["initial_confidence"] = initial_confidence
    normalized_capture["classification_model"] = classification_model
    normalized_capture["description"] = description
    normalized_capture["max_brightness_delta"] = max_brightness_delta
    normalized_capture["mean_brightness"] = mean_brightness

    return normalized, normalized != sidecar


def metadata_for_filter(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Return current V8 fields used by capture browsers."""
    normalized, _changed = normalize_sidecar(sidecar)
    capture = normalized["capture"]
    camera = normalized.get("camera", {})

    site = ""
    if isinstance(camera, dict):
        site = str(camera.get("site_name", "") or "").strip()

    return {
        "verified": capture["verified"],
        "classification": capture["classification"],
        "initial_classification": capture["initial_classification"],
        "type": capture["type"],
        "initial_confidence": capture["initial_confidence"],
        "classification_model": capture["classification_model"],
        "site": site,
        "max_brightness_delta": capture["max_brightness_delta"],
        "mean_brightness": capture["mean_brightness"],
    }
