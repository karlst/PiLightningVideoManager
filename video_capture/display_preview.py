"""
@file display_preview.py

@brief Starts and stops a live camera preview on a monitor attached to the Pi.

DisplayPreview provides a local, full-motion view of the camera for setup and
aiming. It is intended for a monitor physically attached to the Raspberry Pi,
rather than for the browser-based preview used from another computer or tablet.

The class does not read camera frames in Python. Instead, it starts ffplay as a
separate process. ffplay is the video-player program supplied with FFmpeg. It
opens the configured Linux V4L2 camera device directly and displays the live
video using the configured camera format and resolution.

Because the Pi application may be started as a background service rather than
from the graphical desktop, start() explicitly sets DISPLAY=:0. This tells
ffplay to put its window on the Pi's primary graphical display.

DisplayPreview keeps the ffplay process handle so the application can determine
whether the local preview is running and can terminate it when the user stops
the preview.
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