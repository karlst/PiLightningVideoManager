"""
@file cam_config.py

@brief Pi Camera Capture configuration with camera values loaded from JSON.

Camera/device-specific values are loaded from config/camera_config.json when
CamConfig is created. The remaining runtime/system values are intentionally
left in Python for now; system_config.json will be integrated separately.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


CAMERA_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "camera_config.json"
)


# ## Read and validate camera_config.json.
def load_camera_settings() -> dict[str, Any]:
    try:
        data = json.loads(
            CAMERA_CONFIG_PATH.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        return {}
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(
            f"Unable to read camera config: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "camera_config.json must contain a JSON object"
        )

    return data


# ## Atomically write camera settings for future web/configuration use.
def save_camera_settings(
    settings: dict[str, Any],
) -> None:
    CAMERA_CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = CAMERA_CONFIG_PATH.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            settings,
            indent=4,
        ) + "\n",
        encoding="utf-8",
    )

    temporary_path.replace(
        CAMERA_CONFIG_PATH
    )


# ## Camera, capture, trigger, analysis, and storage configuration.
@dataclass
class CamConfig:
    app_version: str = "0.70"

    # Set once by create_app() for the lifetime of the capture application.
    application_start_utc: str = ""

    video_device: str = "/dev/video0"
    input_format: str = "mjpeg"

    frame_rate_fps: int = 260
    frame_width_pixels: int = 640
    frame_height_pixels: int = 360

    buffer_seconds: int = 2
    post_trigger_seconds: int = 1
    capture_seconds: int = 2

    ffmpeg_log_level: str = "warning"
    ffmpeg_hide_banner: bool = True

    root_directory: Path = (
        Path.home() /
        "elpData3709"
    )

    capture_directory: Path = (
        root_directory /
        "captures"
    )

    hls_directory: Path = (
        root_directory /
        "hls"
    )

    event_log_directory: Path = (
        root_directory /
        "logs"
    )

    event_log_file: Path = (
        event_log_directory /
        "event_log.jsonl"
    )

    event_log_max_entries: int = 5000
    event_log_write_timeout_seconds: float = 0.25

    preview_frame_rate_fps: int = 5
    preview_width_pixels: int = 1280
    preview_height_pixels: int = 720

    hls_time_seconds: float = 0.5
    hls_list_size: int = 2

    health_log_interval_seconds: float = 300.0

    brightness_average_frames: int = 100
    metric_history_seconds: int = 36000
    metric_history_sample_seconds: float = 1.0
    motion_changed_pixel_threshold: int = 25

    camera_name: str = "ELP USB Camera"
    camera_type: str = "ELP USB High Speed"
    camera_latitude_degrees: float = 32.2225600
    camera_longitude_degrees: float = -111.5919100
    camera_bearing_degrees: float = 0.0
    camera_hfov_degrees: float = 0.0
    camera_vfov_degrees: float = 0.0
    camera_preview_refresh_seconds: float = 0.2

    trigger_enabled: bool = True

    # Minimum time between automatic trigger events.
    trigger_cooldown_seconds: float = 1.0

    capture_max_files: int = 100
    capture_protect_recent_seconds: float = 60.0

    # ## Overlay camera/device fields from config/camera_config.json.
    def __post_init__(
        self,
    ) -> None:
        settings = load_camera_settings()

        string_fields = (
            "video_device",
            "input_format",
            "camera_name",
            "camera_type",
        )

        integer_fields = (
            "frame_rate_fps",
            "frame_width_pixels",
            "frame_height_pixels",
        )

        float_fields = (
            "camera_latitude_degrees",
            "camera_longitude_degrees",
            "camera_bearing_degrees",
            "camera_hfov_degrees",
            "camera_vfov_degrees",
        )

        for field_name in string_fields:
            if field_name in settings:
                setattr(
                    self,
                    field_name,
                    str(settings[field_name]),
                )

        for field_name in integer_fields:
            if field_name in settings:
                setattr(
                    self,
                    field_name,
                    int(settings[field_name]),
                )

        for field_name in float_fields:
            if field_name in settings:
                setattr(
                    self,
                    field_name,
                    float(settings[field_name]),
                )

    # ## Ensure all configured output directories exist.
    def ensure_directories(
        self
    ) -> None:
        self.root_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        self.capture_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        self.hls_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        self.event_log_directory.mkdir(
            parents=True,
            exist_ok=True
        )
