"""Current Pi Camera sidecar schema helpers."""

from __future__ import annotations

import copy
import math
from typing import Any

SIDECAR_VERSION = 7

CLASSIFICATION_CODE_TO_NAME = {
    "TF": "True Flash",
    "NA": "Noise Anomaly",
    "STA": "Stair-step Anomaly",
    "SSA": "Steady-state Anomaly",
    "FDA": "Frame Dropout Anomaly",
    "NAC": "Not a Candidate",
    "UFA": "Unidentified Flying Anomaly",
}

CLASSIFICATION_NAME_TO_CODE = {
    name: code
    for code, name in CLASSIFICATION_CODE_TO_NAME.items()
}

CLASSIFICATION_CODES = tuple(
    CLASSIFICATION_CODE_TO_NAME
)

LIGHTNING_TYPES = (
    "UK",
    "CG",
    "IC",
    "LCC",
)

# Aliases accepted when normalizing current-schema metadata. These are
# terminology aliases only; this module does not migrate old sidecar schemas.
_CLASSIFICATION_ALIASES = {
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

    "UNIDENTIFIED_FLYING_ANOMALY": "UFA",
}


def _canonical_classification_token(
    value: Any,
) -> str:
    text = str(
        value or ""
    ).strip()

    upper = text.upper()

    if upper in CLASSIFICATION_CODES:
        return upper

    if text in CLASSIFICATION_NAME_TO_CODE:
        return CLASSIFICATION_NAME_TO_CODE[
            text
        ]

    if upper in _CLASSIFICATION_ALIASES:
        return _CLASSIFICATION_ALIASES[
            upper
        ]

    raise RuntimeError(
        f"Unknown classification: {text or '<blank>'}"
    )


def normalize_classification(
    value: Any,
) -> str:
    """Normalize one final code or an H-M-L classification signature."""
    text = str(
        value or ""
    ).strip()

    parts = text.split(
        "-"
    )

    if len(parts) == 1:
        return _canonical_classification_token(
            parts[0]
        )

    if len(parts) == 3:
        normalized_parts: list[str] = []

        for part in parts:
            if str(
                part or ""
            ).strip().upper() == "UNK":
                normalized_parts.append(
                    "UNK"
                )
            else:
                normalized_parts.append(
                    _canonical_classification_token(
                        part
                    )
                )

        return "-".join(
            normalized_parts
        )

    raise RuntimeError(
        "Classification must be one code or an H-M-L three-code signature"
    )


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


def apply_capture_brightness_summary(
    sidecar: dict[str, Any],
) -> bool:
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
    """Normalize a current V7 sidecar without migrating older schemas.

    V7 workflow fields live inside ``capture``:

        capture.verified
        capture.classification
        capture.type
        capture.description

    Older sidecars must be converted first with migrate_capture_files.py.
    """
    if not isinstance(
        sidecar,
        dict,
    ):
        raise TypeError(
            "sidecar must be a dictionary"
        )

    version = sidecar.get(
        "sidecar_version"
    )

    if version != SIDECAR_VERSION:
        raise RuntimeError(
            f"Sidecar version {version!r} is not supported; "
            "run migrate_capture_files.py first"
        )

    capture = sidecar.get(
        "capture"
    )

    if not isinstance(
        capture,
        dict,
    ):
        raise RuntimeError(
            "V7 sidecar is missing capture metadata"
        )

    normalized = copy.deepcopy(
        sidecar
    )
    normalized_capture = normalized[
        "capture"
    ]

    verified = normalized_capture.get(
        "verified"
    )

    if not isinstance(
        verified,
        bool,
    ):
        raise RuntimeError(
            "capture.verified must be boolean"
        )

    classification = normalize_classification(
        normalized_capture.get(
            "classification"
        )
    )

    lightning_type = str(
        normalized_capture.get(
            "type",
            "UK",
        ) or "UK"
    ).strip().upper()

    if lightning_type not in LIGHTNING_TYPES:
        raise RuntimeError(
            f"Unknown lightning type: {lightning_type}"
        )

    description = str(
        normalized_capture.get(
            "description",
            "",
        ) or ""
    )

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
            "V7 capture must contain numeric max_brightness_delta "
            "and mean_brightness"
        ) from error

    if not (
        math.isfinite(max_brightness_delta)
        and math.isfinite(mean_brightness)
    ):
        raise RuntimeError("V7 capture brightness summary values must be finite")

    if max_brightness_delta < 0.0:
        raise RuntimeError("capture.max_brightness_delta must be non-negative")

    normalized_capture[
        "verified"
    ] = verified
    normalized_capture[
        "classification"
    ] = classification
    normalized_capture[
        "type"
    ] = lightning_type
    normalized_capture[
        "description"
    ] = description
    normalized_capture[
        "max_brightness_delta"
    ] = max_brightness_delta
    normalized_capture[
        "mean_brightness"
    ] = mean_brightness

    return (
        normalized,
        normalized != sidecar,
    )


def metadata_for_filter(
    sidecar: dict[str, Any],
) -> dict[str, Any]:
    """Return current V7 fields used by the Capture Editor browser."""
    normalized, _changed = normalize_sidecar(
        sidecar
    )

    capture = normalized[
        "capture"
    ]

    camera = normalized.get(
        "camera",
        {},
    )

    site = ""

    if isinstance(
        camera,
        dict,
    ):
        site = str(
            camera.get(
                "site_name",
                "",
            ) or ""
        ).strip()

    return {
        "verified":
            capture["verified"],
        "classification":
            capture["classification"],
        "type":
            capture["type"],
        "site":
            site,
        "max_brightness_delta":
            capture["max_brightness_delta"],
        "mean_brightness":
            capture["mean_brightness"],
    }
