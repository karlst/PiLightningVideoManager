"""
@file system_config.py

@brief Shared access to installation/runtime settings in config/system_config.json.

The JSON file contains settings that may be changed while Pi Camera Capture is
running. Readers load the file when they need the current value rather than
holding a startup-only copy. Writes are atomic so the capture process and the
independent Pi SolutionFilter service never see a partially written file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "system_config.json"
)

DEFAULT_SETTINGS = {
    "home_directory": "/home/karlst",
    "program_root": "/home/karlst/Documents/videoManager",
    "data_root": "/home/karlst/elpData3709",
    "psf_interval_seconds": 60,
    "save_filtered_false_positives": False,
}


# ## Read current system settings, supplying defaults for missing fields.
def load_system_settings() -> dict[str, Any]:
    settings = dict(
        DEFAULT_SETTINGS
    )

    if not CONFIG_PATH.is_file():
        return settings

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
            f"Unable to read system config: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "system_config.json must contain a JSON object"
        )

    settings.update(
        data
    )

    settings[
        "save_filtered_false_positives"
    ] = bool(
        settings.get(
            "save_filtered_false_positives",
            False,
        )
    )

    return settings


# ## Atomically write a complete system-settings dictionary.
def save_system_settings(
    settings: dict[str, Any],
) -> dict[str, Any]:
    validated = dict(
        DEFAULT_SETTINGS
    )

    validated.update(
        settings
    )

    validated[
        "save_filtered_false_positives"
    ] = bool(
        validated.get(
            "save_filtered_false_positives",
            False,
        )
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

    return validated


# ## Persist whether SolutionFilter rejects are retained in anomaly folders.
def set_save_filtered_false_positives(
    enabled: bool,
) -> dict[str, Any]:
    settings = (
        load_system_settings()
    )

    settings[
        "save_filtered_false_positives"
    ] = bool(
        enabled
    )

    return save_system_settings(
        settings
    )
