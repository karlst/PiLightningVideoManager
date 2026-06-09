"""
@file motion_plugin.py

@brief Frame-to-frame motion/change analysis plugin.
"""

import cv2
import numpy as np

from camera_reader import CameraFrame


class MotionPlugin:
    """
    @brief Computes frame difference metrics.

    @note This measures scene change, not true object motion.
    """

    def __init__(
        self,
        changed_pixel_threshold: int = 25
    ) -> None:
        self._changed_pixel_threshold = changed_pixel_threshold
        self._previous_gray_frame = None

    def analyze(
        self,
        camera_frame: CameraFrame
    ) -> dict:
        gray_frame = cv2.cvtColor(
            camera_frame.frame,
            cv2.COLOR_BGR2GRAY
        )

        frame_difference_mean = 0.0
        changed_pixel_count = 0
        changed_pixel_fraction = 0.0

        if self._previous_gray_frame is not None:
            difference_frame = cv2.absdiff(
                gray_frame,
                self._previous_gray_frame
            )

            frame_difference_mean = float(
                difference_frame.mean()
            )

            changed_pixel_count = int(
                np.count_nonzero(
                    difference_frame > self._changed_pixel_threshold
                )
            )

            total_pixel_count = (
                difference_frame.shape[0] *
                difference_frame.shape[1]
            )

            changed_pixel_fraction = (
                changed_pixel_count /
                total_pixel_count
            )

        self._previous_gray_frame = gray_frame

        return {
            "frame_difference_mean": frame_difference_mean,
            "changed_pixel_count": changed_pixel_count,
            "changed_pixel_fraction": changed_pixel_fraction
        }