"""
@file frame_analyzer.py

@brief Plugin-based camera frame analyzer.
"""

from typing import Protocol

from video_capture.camera_reader import CameraFrame


class AnalysisPlugin(Protocol):
    """
    @brief Interface for frame analysis plugins.
    """

    def analyze(
        self,
        camera_frame: CameraFrame
    ) -> dict:
        ...


class FrameAnalyzer:
    """
    @brief Runs analysis plugins on camera frames.
    """

    def __init__(self) -> None:
        self._plugins: list[AnalysisPlugin] = []

    def add_plugin(
        self,
        plugin: AnalysisPlugin
    ) -> None:
        self._plugins.append(
            plugin
        )

    def analyze(
        self,
        camera_frame: CameraFrame
    ) -> dict:
        result = {
            "sequence_number": camera_frame.sequence_number,
            "timestamp_utc": camera_frame.timestamp_utc,
            "timestamp_monotonic": camera_frame.timestamp_monotonic
        }

        for plugin in self._plugins:
            plugin_result = plugin.analyze(
                camera_frame
            )

            result.update(
                plugin_result
            )

        return result