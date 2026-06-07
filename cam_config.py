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