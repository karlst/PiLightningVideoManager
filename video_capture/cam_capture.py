"""
@file cam_capture.py

@brief Performs a direct, fixed-duration camera recording using FFmpeg.

CamCapture is a simple camera-recording helper used to ask FFmpeg to capture
directly from the configured Linux V4L2 camera device. Unlike the normal
BufferManager/ClipWriter path, it does not use the application's rolling frame
buffer or trigger logic; FFmpeg reads the camera itself and writes the camera
stream directly to an MKV file.
"""

from datetime import datetime, timezone
from pathlib import Path
import subprocess

from video_capture.cam_config import CamConfig
from video_capture.utils import utc_now


class CamCapture:
    """
    Controls ffmpeg capture from a USB camera.
    """

    def __init__(self, config: CamConfig) -> None:
        self._config = config

    def capture_once(self) -> int:
        """
        Capture one video clip.

        Returns:
            ffmpeg process return code.
        """

        return_code = 0

        self._config.video_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        output_file = self._create_output_file_path()

        print(f"{utc_now()} START camera capture")
        print(f"Output file: {output_file}")

        result = subprocess.run(
            self._create_ffmpeg_command(output_file)
        )

        print(f"{utc_now()} STOP camera capture")
        print(f"ffmpeg exit code: {result.returncode}")

        return_code = result.returncode

        return return_code

    def _create_output_file_path(self) -> Path:
        filename = datetime.now(timezone.utc).strftime(
            "capture_%Y%m%dT%H%M%SZ.mkv"
        )

        output_file = self._config.video_directory / filename

        return output_file

    def _create_ffmpeg_command(self, output_file: Path) -> list[str]:
        config = self._config

        command = [
            "ffmpeg",
        ]

        if config.ffmpeg_hide_banner:
            command.append("-hide_banner")

        command += [
            "-loglevel",
            config.ffmpeg_log_level,
            "-f",
            "v4l2",
            "-framerate",
            str(config.frame_rate_fps),
            "-video_size",
            (
                f"{config.frame_width_pixels}"
                f"x{config.frame_height_pixels}"
            ),
            "-input_format",
            config.input_format,
            "-i",
            config.video_device,
            "-t",
            str(config.capture_seconds),
            "-c",
            "copy",
            str(output_file),
        ]

        return command