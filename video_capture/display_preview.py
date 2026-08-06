"""
@file display_preview.py

@brief Starts/stops ffplay preview on the Pi attached monitor.
"""

import os
import subprocess

from video_capture.cam_config import CamConfig


class DisplayPreview:
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config
        self._process: subprocess.Popen | None = None

    def is_running(self) -> bool:
        running = False

        if self._process is not None:
            running = self._process.poll() is None

        return running

    def start(self) -> tuple[bool, str]:
        success = False
        message = "Display preview already running"

        if not self.is_running():
            env = os.environ.copy()
            env["DISPLAY"] = ":0"

            command = [
                "ffplay",
                "-f",
                "v4l2",
                "-input_format",
                self._config.input_format,
                "-video_size",
                (
                    f"{self._config.frame_width_pixels}"
                    f"x{self._config.frame_height_pixels}"
                ),
                self._config.video_device,
            ]

            self._process = subprocess.Popen(
                command,
                env=env
            )

            success = True
            message = "Display preview started"

        return success, message

    def stop(self) -> tuple[bool, str]:
        success = False
        message = "Display preview was not running"

        if self.is_running():
            self._process.terminate()
            self._process.wait(
                timeout=5
            )
            self._process = None

            success = True
            message = "Display preview stopped"

        return success, message