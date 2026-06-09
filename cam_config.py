from dataclasses import dataclass
from pathlib import Path


@dataclass
class CamConfig:
    video_device: str = "/dev/video0"
    input_format: str = "mjpeg"

    buffer_seconds: int = 5
    post_trigger_seconds: int = 1

    frame_rate_fps: int = 260
    frame_width_pixels: int = 640
    frame_height_pixels: int = 360

    capture_seconds: int = 2

    ffmpeg_log_level: str = "warning"
    ffmpeg_hide_banner: bool = True

    video_directory: Path = (
        Path.home() / "Documents" / "video"
    )

    preview_frame_rate_fps: int = 5
    preview_width_pixels: int = 1280
    preview_height_pixels: int = 720

    hls_time_seconds = 0.5
    hls_list_size: int = 2
    hls_directory: Path = Path.home() / "Documents" / "videoManager" / "hls"

    buffer_seconds: int = 2

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