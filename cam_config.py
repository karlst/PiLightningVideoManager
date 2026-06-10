from dataclasses import dataclass
from pathlib import Path


@dataclass
class CamConfig:
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
    metric_history_seconds: int = 3600
    metric_history_sample_seconds: float = 1.0
    motion_changed_pixel_threshold: int = 25

    camera_name: str = "ELP USB Camera"
    camera_latitude_degrees: float = 32.2225600
    camera_longitude_degrees: float = -111.5919100
    camera_bearing_degrees: float = 0.0
    camera_hfov_degrees: float = 0.0
    camera_vfov_degrees: float = 0.0
    camera_preview_refresh_seconds: float = 0.2

    trigger_enabled: bool = True

    trigger_brightness_increase_percent: float = 10.0
    trigger_min_brightness: float = 5.0

    trigger_brightness_delta_increase_percent: float = 1.0
    trigger_motion_increase_percent: float = 1.0

    trigger_min_brightness_delta: float = 0.01
    trigger_min_changed_pixel_fraction: float = 0.001

    trigger_cooldown_seconds: float = 5.0

    capture_max_files: int = 100
    capture_protect_recent_seconds: float = 60.0

    def ensure_directories(self) -> None:
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