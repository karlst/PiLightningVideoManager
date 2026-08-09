"""
@file frame_analyzer.py

@brief Runs a configurable set of analysis plugins on each camera frame.

FrameAnalyzer provides a small plugin architecture so frame measurements can be
added or removed without changing the camera capture pipeline.  A plugin is any
object that implements analyze(camera_frame) and returns a dictionary containing
the measurements it calculated for that frame.

Plugins are registered with add_plugin().  Each time analyze() is called,
FrameAnalyzer passes the same CameraFrame to every registered plugin in order.
The dictionaries returned by the plugins are merged into one result dictionary,
along with the frame sequence number and timestamps.  This lets independent
analysis modules contribute metrics such as brightness or other image properties
while BufferManager and the rest of the capture system consume one combined
per-frame metric record.
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