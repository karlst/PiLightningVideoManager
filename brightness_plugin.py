"""
@file brightness_plugin.py

@brief Brightness analysis plugin.
"""

import cv2
import numpy as np

from camera_reader import CameraFrame
from moving_average import MovingAverage


class BrightnessPlugin:
    """
    @brief Computes frame brightness metrics.
    """

    def __init__(
        self,
        average_window_frames: int,
        bright_pixel_threshold: int = 240
    ) -> None:
        self._moving_average = MovingAverage(
            average_window_frames
        )

        self._bright_pixel_threshold = bright_pixel_threshold

    def analyze(
        self,
        camera_frame: CameraFrame
    ) -> dict:
        gray_frame = cv2.cvtColor(
            camera_frame.frame,
            cv2.COLOR_BGR2GRAY
        )

        mean_brightness = float(
            gray_frame.mean()
        )

        max_brightness = int(
            gray_frame.max()
        )

        moving_average_brightness = (
            self._moving_average.push(
                mean_brightness
            )
        )

        brightness_delta = (
            mean_brightness -
            moving_average_brightness
        )

        bright_pixel_count = int(
            np.count_nonzero(
                gray_frame > self._bright_pixel_threshold
            )
        )

        total_pixel_count = (
            gray_frame.shape[0] *
            gray_frame.shape[1]
        )

        bright_pixel_fraction = (
            bright_pixel_count /
            total_pixel_count
        )

        result = {
            "mean_brightness": mean_brightness,
            "max_brightness": max_brightness,
            "moving_average_brightness": moving_average_brightness,
            "brightness_delta": brightness_delta,
            "bright_pixel_count": bright_pixel_count,
            "bright_pixel_fraction": bright_pixel_fraction
        }

        return result