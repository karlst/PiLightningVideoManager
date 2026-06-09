"""
@file buffer_manager.py

@brief Coordinates CameraReader, RingBuffer, ClipWriter, and frame analysis.
"""

from pathlib import Path

from brightness_plugin import BrightnessPlugin
from cam_config import CamConfig
from camera_reader import CameraFrame
from camera_reader import CameraReader
from clip_writer import ClipWriter
from frame_analyzer import FrameAnalyzer
from metric_history import MetricHistory
from motion_plugin import MotionPlugin
from ring_buffer import RingBuffer


class BufferManager:
    """
    @brief Owns camera buffering and analysis components.
    """

    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config

        self._capacity_frames = (
            config.frame_rate_fps *
            config.buffer_seconds
        )

        self._metric_history_capacity = int(
            config.metric_history_seconds /
            config.metric_history_sample_seconds
        )

        self._ring_buffer = RingBuffer(
            capacity=self._capacity_frames
        )

        self._metric_history = MetricHistory(
            capacity=self._metric_history_capacity
        )

        self._frame_analyzer = FrameAnalyzer()

        self._frame_analyzer.add_plugin(
            BrightnessPlugin(
                average_window_frames=config.brightness_average_frames
            )
        )

        self._frame_analyzer.add_plugin(
            MotionPlugin(
                changed_pixel_threshold=config.motion_changed_pixel_threshold
            )
        )

        self._camera_reader = CameraReader(
            config,
            on_frame=self._on_frame
        )

        self._clip_writer = ClipWriter(
            output_directory=(
                Path.home() /
                "Documents" /
                "videoManager" /
                "captures"
            ),
            frame_rate_fps=config.frame_rate_fps
        )

        self._last_metric_time_monotonic: float = 0.0

    def start(self) -> tuple[bool, str]:
        success = False
        message = "Buffer already running"

        if not self.is_running():
            self._ring_buffer.clear()
            self._metric_history.clear()

            success, message = (
                self._camera_reader.start()
            )

        return success, message

    def stop(self) -> tuple[bool, str]:
        success, message = (
            self._camera_reader.stop()
        )

        return success, message

    def clear(self) -> tuple[bool, str]:
        success = False
        message = "Buffer is running; stop before clearing"

        if not self.is_running():
            self._ring_buffer.clear()
            self._metric_history.clear()

            success = True
            message = "Buffer cleared"

        return success, message

    def capture(self) -> tuple[bool, str, dict]:
        frames = (
            self._ring_buffer.snapshot()
        )

        success, message, writer_status = (
            self._clip_writer.write_frames(
                frames
            )
        )

        capture_status = {
            "buffer_count": len(
                frames
            ),
            **writer_status
        }

        if len(frames) > 0:
            first_frame = frames[0]
            last_frame = frames[-1]

            duration_seconds = (
                last_frame.timestamp_monotonic -
                first_frame.timestamp_monotonic
            )

            capture_status.update(
                {
                    "first_sequence_number":
                        first_frame.sequence_number,
                    "last_sequence_number":
                        last_frame.sequence_number,
                    "first_timestamp_utc":
                        first_frame.timestamp_utc,
                    "last_timestamp_utc":
                        last_frame.timestamp_utc,
                    "duration_seconds":
                        duration_seconds
                }
            )

        return success, message, capture_status

    def is_running(self) -> bool:
        return self._camera_reader.is_running()

    def get_metrics_history(self) -> list[dict]:
        return self._metric_history.snapshot()

    def get_status(self) -> dict:
        reader_status = (
            self._camera_reader.get_status()
        )

        buffer_status = (
            self._ring_buffer.get_status()
        )

        metric_status = (
            self._metric_history.get_status()
        )

        status = {
            "running": reader_status["running"],
            "frame_count": reader_status["frame_count"],
            "failed_read_count": reader_status["failed_read_count"],
            "estimated_fps": reader_status["estimated_fps"],
            "elapsed_seconds": reader_status["elapsed_seconds"],
            "seconds_since_last_frame": reader_status["seconds_since_last_frame"],
            "last_error": reader_status["last_error"],
            "buffer_capacity": buffer_status["capacity"],
            "buffer_count": buffer_status["count"],
            "buffer_full": buffer_status["full"],
            "buffer_total_pushed": buffer_status["total_pushed"],
            "buffer_overwrite_count": buffer_status["overwrite_count"],
            "oldest_sequence_number": buffer_status["oldest_sequence_number"],
            "newest_sequence_number": buffer_status["newest_sequence_number"],
            "metric_history_capacity": metric_status["capacity"],
            "metric_history_count": metric_status["count"],
            "metric_history_overwrite_count": metric_status["overwrite_count"]
        }

        return status

    def _on_frame(
        self,
        camera_frame: CameraFrame
    ) -> None:
        self._ring_buffer.push(
            camera_frame
        )

        should_sample_metric = (
            (
                camera_frame.timestamp_monotonic -
                self._last_metric_time_monotonic
            ) >= self._config.metric_history_sample_seconds
        )

        if should_sample_metric:
            metric = self._frame_analyzer.analyze(
                camera_frame
            )

            self._metric_history.push(
                metric
            )

            self._last_metric_time_monotonic = (
                camera_frame.timestamp_monotonic
            )