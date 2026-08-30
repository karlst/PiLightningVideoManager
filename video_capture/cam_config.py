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
import math
from pathlib import Path
from typing import Any

from version import VERSION
from common.system_config import load_system_settings


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



# ## Validate and atomically persist camera geometry settings.
def update_camera_geometry_settings(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    hfov_degrees: float,
    vfov_degrees: float,
) -> dict[str, Any]:
    latitude_degrees = float(
        latitude_degrees
    )
    longitude_degrees = float(
        longitude_degrees
    )
    bearing_degrees = float(
        bearing_degrees
    )
    hfov_degrees = float(
        hfov_degrees
    )
    vfov_degrees = float(
        vfov_degrees
    )

    if not -90.0 <= latitude_degrees <= 90.0:
        raise ValueError(
            "Latitude must be between -90 and 90 degrees"
        )

    if not -180.0 <= longitude_degrees <= 180.0:
        raise ValueError(
            "Longitude must be between -180 and 180 degrees"
        )

    if not 0.0 <= bearing_degrees < 360.0:
        raise ValueError(
            "Bearing must be at least 0 and less than 360 degrees"
        )

    if not 0.0 <= hfov_degrees <= 360.0:
        raise ValueError(
            "Horizontal FOV must be between 0 and 360 degrees"
        )

    if not 0.0 <= vfov_degrees <= 180.0:
        raise ValueError(
            "Vertical FOV must be between 0 and 180 degrees"
        )

    settings = (
        load_camera_settings()
    )

    settings[
        "camera_latitude_degrees"
    ] = latitude_degrees

    settings[
        "camera_longitude_degrees"
    ] = longitude_degrees

    settings[
        "camera_bearing_degrees"
    ] = bearing_degrees

    settings[
        "camera_hfov_degrees"
    ] = hfov_degrees

    settings[
        "camera_vfov_degrees"
    ] = vfov_degrees

    save_camera_settings(
        settings
    )

    return settings


# ## Return whether a compass bearing lies inside a clockwise angular sector.
def _bearing_in_sector(
    bearing_degrees: float,
    left_degrees: float,
    right_degrees: float,
) -> bool:
    bearing = (
        float(
            bearing_degrees
        ) %
        360.0
    )

    left = (
        float(
            left_degrees
        ) %
        360.0
    )

    right = (
        float(
            right_degrees
        ) %
        360.0
    )

    if left <= right:
        return (
            left <=
            bearing <=
            right
        )

    return (
        bearing >= left or
        bearing <= right
    )


# ## Project one bearing/range point from the camera on a spherical Earth.
def _destination_point(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    distance_miles: float,
) -> tuple[float, float]:
    earth_radius_miles = 3958.7613

    latitude_radians = math.radians(
        latitude_degrees
    )

    longitude_radians = math.radians(
        longitude_degrees
    )

    bearing_radians = math.radians(
        bearing_degrees
    )

    angular_distance = (
        float(
            distance_miles
        ) /
        earth_radius_miles
    )

    destination_latitude = math.asin(
        (
            math.sin(
                latitude_radians
            ) *
            math.cos(
                angular_distance
            )
        ) +
        (
            math.cos(
                latitude_radians
            ) *
            math.sin(
                angular_distance
            ) *
            math.cos(
                bearing_radians
            )
        )
    )

    destination_longitude = (
        longitude_radians +
        math.atan2(
            (
                math.sin(
                    bearing_radians
                ) *
                math.sin(
                    angular_distance
                ) *
                math.cos(
                    latitude_radians
                )
            ),
            (
                math.cos(
                    angular_distance
                ) -
                (
                    math.sin(
                        latitude_radians
                    ) *
                    math.sin(
                        destination_latitude
                    )
                )
            ),
        )
    )

    longitude_degrees_result = (
        (
            math.degrees(
                destination_longitude
            ) +
            540.0
        ) %
        360.0
    ) - 180.0

    return (
        math.degrees(
            destination_latitude
        ),
        longitude_degrees_result,
    )


# ## Build a conservative rectangular search box around the camera FOV sector.
def build_search_bounding_box(
    latitude_degrees: float,
    longitude_degrees: float,
    bearing_degrees: float,
    hfov_degrees: float,
    minimum_range_miles: float,
    maximum_range_miles: float,
) -> dict[str, float]:
    minimum_range = max(
        0.0,
        float(
            minimum_range_miles
        )
    )

    maximum_range = max(
        minimum_range,
        float(
            maximum_range_miles
        )
    )

    half_fov = max(
        0.0,
        min(
            180.0,
            float(
                hfov_degrees
            ) /
            2.0,
        )
    )

    left_bearing = (
        float(
            bearing_degrees
        ) -
        half_fov
    ) % 360.0

    right_bearing = (
        float(
            bearing_degrees
        ) +
        half_fov
    ) % 360.0

    bearings = [
        left_bearing,
        float(
            bearing_degrees
        ) % 360.0,
        right_bearing,
    ]

    # Cardinal directions can be extrema of the enclosing latitude/longitude
    # rectangle even when they are not the two FOV edge bearings.
    for cardinal_bearing in (
        0.0,
        90.0,
        180.0,
        270.0,
    ):
        if _bearing_in_sector(
            cardinal_bearing,
            left_bearing,
            right_bearing,
        ):
            bearings.append(
                cardinal_bearing
            )

    points: list[tuple[float, float]] = []

    for range_miles in (
        minimum_range,
        maximum_range,
    ):
        for search_bearing in bearings:
            points.append(
                _destination_point(
                    latitude_degrees,
                    longitude_degrees,
                    search_bearing,
                    range_miles,
                )
            )

    latitudes = [
        point[0]
        for point in points
    ]

    longitudes = [
        point[1]
        for point in points
    ]

    return {
        "minimum_range_miles":
            minimum_range,

        "maximum_range_miles":
            maximum_range,

        "min_latitude_degrees":
            round(
                min(
                    latitudes
                ),
                7
            ),

        "max_latitude_degrees":
            round(
                max(
                    latitudes
                ),
                7
            ),

        "min_longitude_degrees":
            round(
                min(
                    longitudes
                ),
                7
            ),

        "max_longitude_degrees":
            round(
                max(
                    longitudes
                ),
                7
            ),
    }


# ## Camera, capture, trigger, analysis, and storage configuration.
@dataclass
class CamConfig:
    app_version: str = VERSION

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
    camera_site_name: str = "Flagstaff"
    camera_latitude_degrees: float = 32.2225600
    camera_longitude_degrees: float = -111.5919100
    camera_bearing_degrees: float = 0.0
    camera_hfov_degrees: float = 0.0
    camera_vfov_degrees: float = 0.0

    # Conservative rectangular geographic search area used to look up a
    # captured flash in an external lightning-detection database.
    search_minimum_range_miles: float = 1.0
    search_maximum_range_miles: float = 25.0

    camera_preview_refresh_seconds: float = 0.2

    trigger_enabled: bool = True

    # Wait time after capture to analyze and write capture data - avoids thread starvation
    # of camera reader
    capture_write_delay_seconds: float = 2.0

    # Minimum time between automatic trigger events.
    trigger_cooldown_seconds: float = 1.0

    capture_max_files: int = 100
    capture_protect_recent_seconds: float = 60.0

    # ## Overlay camera/device fields from config/camera_config.json.
    def __post_init__(
        self,
    ) -> None:
        # PI PACKAGE DATA-ROOT FIX 2026-08-29
        # The installer writes the machine-specific data_root to
        # config/system_config.json. Use that as the runtime source of truth
        # instead of the legacy ~/elpData3709 class defaults.
        system_settings = load_system_settings()

        data_root = str(
            system_settings.get(
                "data_root",
                ""
            )
        ).strip()

        if data_root:
            self.root_directory = Path(
                data_root
            ).expanduser()

            self.capture_directory = (
                self.root_directory /
                "captures"
            )

            self.hls_directory = (
                self.root_directory /
                "hls"
            )

            self.event_log_directory = (
                self.root_directory /
                "logs"
            )

            self.event_log_file = (
                self.event_log_directory /
                "event_log.jsonl"
            )

        settings = load_camera_settings()

        string_fields = (
            "video_device",
            "input_format",
            "camera_name",
            "camera_type",
            "camera_site_name",
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
            "search_minimum_range_miles",
            "search_maximum_range_miles",
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
