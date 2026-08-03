from dataclasses import dataclass
from pathlib import Path
from common import TRIGGER_CONFIG


# ## Camera, capture, trigger, analysis, and storage configuration.
@dataclass
class CamConfig:
    app_version: str = "0.67"

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

    # OpenCV connected-component analysis.
    opencv_enabled: bool = True

    # Absolute brightness catches high-contrast night lightning.
    opencv_bright_threshold: int = 220

    # Local contrast catches daylight lightning that is brighter than
    # nearby cloud but not necessarily bright in absolute terms.
    opencv_local_contrast_threshold: int = 25
    opencv_local_contrast_window_pixels: int = 31

    # Component geometry filters. These define a valid component.
    opencv_min_component_area: int = 20
    opencv_min_component_height: int = 20
    opencv_min_component_aspect: float = 2.0

    # Allowed gap when converting valid-component frames to event duration.
    opencv_event_max_missing_frames: int = 3

    camera_name: str = "ELP USB Camera"
    camera_latitude_degrees: float = 32.2225600
    camera_longitude_degrees: float = -111.5919100
    camera_bearing_degrees: float = 0.0
    camera_hfov_degrees: float = 0.0
    camera_vfov_degrees: float = 0.0
    camera_preview_refresh_seconds: float = 0.2

    trigger_enabled: bool = True

     # Minimum time between automatic trigger events.
    trigger_cooldown_seconds: float = 1.0

    trigger_brightness_threshold: float = (
        TRIGGER_CONFIG.trigger_brightness_threshold
    )

    trigger_brightness_delta_threshold: float = (
        TRIGGER_CONFIG.trigger_brightness_delta_threshold
    )

    trigger_changed_pixel_fraction_threshold: float = (
        TRIGGER_CONFIG.trigger_changed_pixel_fraction_threshold
    )

    capture_max_files: int = 100
    capture_protect_recent_seconds: float = 60.0

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
