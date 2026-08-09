"""
Small random-access OpenCV reader used by the desktop Analyzer.

AnalyzerWindow needs to jump directly to arbitrary frames as the user moves the
slider or presses frame-navigation keys. VideoReader owns one OpenCV
VideoCapture object, seeks it to the requested zero-based frame index, decodes
that frame, and returns it as a NumPy/OpenCV image.

It deliberately handles only video-frame access; metadata and sidecar loading
belong to CaptureData.
"""


from pathlib import Path

import cv2
import numpy as np


class VideoReader:
    def __init__(
        self,
        video_path: Path,
    ) -> None:
        self._video_path = video_path
        self._capture = cv2.VideoCapture(
            str(video_path)
        )

        if not self._capture.isOpened():
            raise RuntimeError(
                f"OpenCV could not open: {video_path}"
            )

    def read_frame(
        self,
        frame_index: int,
    ) -> np.ndarray | None:
        self._capture.set(
            cv2.CAP_PROP_POS_FRAMES,
            int(frame_index),
        )

        success, frame = self._capture.read()

        if not success:
            return None

        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
