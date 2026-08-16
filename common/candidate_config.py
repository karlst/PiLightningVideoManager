"""
@file candidate_config.py

@brief Shared CandidateFinder configuration loaded from config/candidate_config.json.

The JSON file is the persistent source of truth. CandidateFinder itself never
reads the file; it receives an immutable CandidateConfig object containing the
effective thresholds for the currently selected sensitivity level.

Sensitivity selects matching entries from the two threshold arrays:

    high   -> index 0
    medium -> index 1
    low    -> index 2

This keeps file I/O out of the per-frame trigger path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "candidate_config.json"
)

SENSITIVITY_INDEX = {
    "high": 0,
    "medium": 1,
    "low": 2,
}

DEFAULT_SETTINGS = {
    "sensitivity": "medium",
    "candidate_brightness_threshold": 999.0,
    "candidate_brightness_delta_thresholds": [
        2.0,
        2.5,
        4.5,
    ],
    "candidate_bright_pixel_delta_threshold": 10.0,
    "candidate_bright_pixel_fraction_thresholds": [
        0.002,
        0.01,
        0.1,
    ],
}


@dataclass(frozen=True)
class CandidateConfig:
    """Effective thresholds used by CandidateFinder for one sensitivity level."""

    sensitivity: str = "medium"

    candidate_brightness_threshold: float = 999.0
    candidate_brightness_delta_threshold: float = 2.5

    candidate_bright_pixel_delta_threshold: float = 10.0
    candidate_bright_pixel_fraction_threshold: float = 0.01


# ## Validate and normalize the persistent candidate settings dictionary.
def validate_candidate_settings(
    settings: dict[str, Any],
) -> dict[str, Any]:
    sensitivity = str(
        settings.get(
            "sensitivity",
            DEFAULT_SETTINGS["sensitivity"],
        )
    ).lower()

    if sensitivity not in SENSITIVITY_INDEX:
        raise ValueError(
            "Sensitivity must be high, medium, or low"
        )

    brightness_threshold = float(
        settings.get(
            "candidate_brightness_threshold",
            DEFAULT_SETTINGS[
                "candidate_brightness_threshold"
            ],
        )
    )

    bright_pixel_delta_threshold = float(
        settings.get(
            "candidate_bright_pixel_delta_threshold",
            DEFAULT_SETTINGS[
                "candidate_bright_pixel_delta_threshold"
            ],
        )
    )

    brightness_delta_thresholds = [
        float(value)
        for value in settings.get(
            "candidate_brightness_delta_thresholds",
            DEFAULT_SETTINGS[
                "candidate_brightness_delta_thresholds"
            ],
        )
    ]

    bright_pixel_fraction_thresholds = [
        float(value)
        for value in settings.get(
            "candidate_bright_pixel_fraction_thresholds",
            DEFAULT_SETTINGS[
                "candidate_bright_pixel_fraction_thresholds"
            ],
        )
    ]

    if len(brightness_delta_thresholds) != 3:
        raise ValueError(
            "candidate_brightness_delta_thresholds must contain 3 values"
        )

    if len(bright_pixel_fraction_thresholds) != 3:
        raise ValueError(
            "candidate_bright_pixel_fraction_thresholds must contain 3 values"
        )

    if brightness_threshold < 0.0:
        raise ValueError(
            "candidate_brightness_threshold must be >= 0"
        )

    if any(
        value < 0.0
        for value in brightness_delta_thresholds
    ):
        raise ValueError(
            "Brightness delta thresholds must be >= 0"
        )

    if not (
        0.0 <=
        bright_pixel_delta_threshold <=
        255.0
    ):
        raise ValueError(
            "candidate_bright_pixel_delta_threshold must be between 0 and 255"
        )

    if any(
        not 0.0 <= value <= 1.0
        for value in bright_pixel_fraction_thresholds
    ):
        raise ValueError(
            "Bright pixel fraction thresholds must be between 0 and 1"
        )

    return {
        "sensitivity": sensitivity,
        "candidate_brightness_threshold":
            brightness_threshold,
        "candidate_brightness_delta_thresholds":
            brightness_delta_thresholds,
        "candidate_bright_pixel_delta_threshold":
            bright_pixel_delta_threshold,
        "candidate_bright_pixel_fraction_thresholds":
            bright_pixel_fraction_thresholds,
    }


# ## Read persistent settings, falling back to built-in defaults if the file is absent.
def load_candidate_settings() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return validate_candidate_settings(
            DEFAULT_SETTINGS
        )

    try:
        data = json.loads(
            CONFIG_PATH.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(
            f"Unable to read candidate config: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "candidate_config.json must contain a JSON object"
        )

    try:
        return validate_candidate_settings(
            data
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise RuntimeError(
            f"Invalid candidate config: {error}"
        ) from error


# ## Convert persistent settings into the effective immutable CandidateConfig.
def candidate_config_from_settings(
    settings: dict[str, Any],
) -> CandidateConfig:
    settings = validate_candidate_settings(
        settings
    )

    sensitivity = settings["sensitivity"]
    index = SENSITIVITY_INDEX[
        sensitivity
    ]

    return CandidateConfig(
        sensitivity=sensitivity,
        candidate_brightness_threshold=(
            settings[
                "candidate_brightness_threshold"
            ]
        ),
        candidate_brightness_delta_threshold=(
            settings[
                "candidate_brightness_delta_thresholds"
            ][index]
        ),
        candidate_bright_pixel_delta_threshold=(
            settings[
                "candidate_bright_pixel_delta_threshold"
            ]
        ),
        candidate_bright_pixel_fraction_threshold=(
            settings[
                "candidate_bright_pixel_fraction_thresholds"
            ][index]
        ),
    )


# ## Load the active CandidateConfig from config/candidate_config.json.
def load_candidate_config() -> CandidateConfig:
    return candidate_config_from_settings(
        load_candidate_settings()
    )


# ## Atomically persist a validated candidate settings dictionary.
def save_candidate_settings(
    settings: dict[str, Any],
) -> CandidateConfig:
    validated = validate_candidate_settings(
        settings
    )

    CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = CONFIG_PATH.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            validated,
            indent=4,
        ) + "\n",
        encoding="utf-8",
    )

    temporary_path.replace(
        CONFIG_PATH
    )

    return candidate_config_from_settings(
        validated
    )


# ## Change only the selected sensitivity and return the new effective config.
def set_candidate_sensitivity(
    sensitivity: str,
) -> CandidateConfig:
    settings = load_candidate_settings()
    settings["sensitivity"] = str(
        sensitivity
    ).lower()

    return save_candidate_settings(
        settings
    )


# ## Restore the shipped candidate settings and return the resulting config.
def reset_candidate_settings() -> CandidateConfig:
    return save_candidate_settings(
        DEFAULT_SETTINGS
    )


# ## Return the effective thresholds for one named sensitivity profile.
def get_sensitivity_config(
    sensitivity: str,
) -> CandidateConfig:
    settings = load_candidate_settings()

    normalized = str(
        sensitivity
    ).lower()

    if normalized not in SENSITIVITY_INDEX:
        raise ValueError(
            "Sensitivity must be high, medium, or low"
        )

    settings[
        "sensitivity"
    ] = normalized

    return candidate_config_from_settings(
        settings
    )


CANDIDATE_CONFIG = load_candidate_config()
