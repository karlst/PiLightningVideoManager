import subprocess
from pathlib import Path

from video_capture.cam_config import CamConfig


class PreviewServer:
    """
    Controls HLS preview generation using ffmpeg.
    """

    def __init__(self, config: CamConfig) -> None:
        self._config = config
        self._process: subprocess.Popen | None = None

    def is_running(self) -> bool:
        running = False

        if self._process is not None:
            running = self._process.poll() is None

        return running

    def start(self) -> tuple[bool, str]:
        success = False
        message = "Preview already running"

        if not self.is_running():
            self._config.hls_directory.mkdir(
                parents=True,
                exist_ok=True
            )

            self._process = subprocess.Popen(
                self._create_ffmpeg_command()
            )

            success = True
            message = "Preview started"

        return success, message

    def stop(self) -> tuple[bool, str]:
        success = False
        message = "Preview was not running"

        if self.is_running():
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None

            success = True
            message = "Preview stopped"

        return success, message

    def _create_ffmpeg_command(self) -> list[str]:
        config = self._config

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            config.ffmpeg_log_level,
            "-f",
            "v4l2",
            "-framerate",
            str(config.preview_frame_rate_fps),
            "-video_size",
            (
                f"{config.preview_width_pixels}"
                f"x{config.preview_height_pixels}"
            ),
            "-input_format",
            config.input_format,
            "-i",
            config.video_device,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-f",
            "hls",
            "-hls_time",
            str(config.hls_time_seconds),
            "-hls_list_size",
            str(config.hls_list_size),
            "-hls_flags",
            "delete_segments",
            str(config.hls_directory / "stream.m3u8"),
        ]

        return command