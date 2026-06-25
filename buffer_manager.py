"""
@file buffer_manager.py

@brief Coordinates CameraReader, RingBuffer, ClipWriter, frame analysis,
trigger evaluation, and event logging.
"""

from pathlib import Path

import cv2

from brightness_plugin import BrightnessPlugin
from bright_component_analyzer import BrightComponentAnalyzer
from cam_config import CamConfig
from camera_reader import CameraFrame
from camera_reader import CameraReader
from clip_writer import ClipWriter
from event_log import EventLog
from frame_analyzer import FrameAnalyzer
from metric_history import MetricHistory
from motion_plugin import MotionPlugin
from ring_buffer import RingBuffer
from trigger_manager import TriggerManager
from capture_manager import CaptureManager


class BufferManager:
    """
    @brief Owns camera buffering, analysis, trigger, and capture components.
    """

    def __init__(
        self,
        config: CamConfig,
        trigger_manager: TriggerManager,
        event_log: EventLog,
        capture_manager: CaptureManager
    ) -> None:
        self._config = config
        self._trigger_manager = trigger_manager
        self._event_log = event_log
        self._capture_manager = capture_manager
        
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

        self._bright_component_analyzer = BrightComponentAnalyzer(
            config
        )

        self._camera_reader = CameraReader(
            config,
            on_frame=self._on_frame
        )

        self._clip_writer = ClipWriter(
            output_directory=
                config.capture_directory,
            frame_rate_fps=
                config.frame_rate_fps
        )

        self._last_metric_time_monotonic: float = 0.0
        self._last_health_log_time_monotonic: float = 0.0
        self._last_logged_error: str = ""

    def start(self) -> tuple[bool, str]:
        success = False
        message = "Buffer already running"

        if not self.is_running():
            self._ring_buffer.clear()
            self._metric_history.clear()

            success, message = (
                self._camera_reader.start()
            )

        if success:
            self._event_log.add(
                "CameraReader started"
            )
        else:
            self._event_log.add(
                f"CameraReader start failed: {message}",
                "error"
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

        sidecar_data = None

        if success:
            output_file = writer_status.get(
                "output_file"
            )

            # Analyze the raw captured frames directly and write the JSON
            # sidecar next to the MP4. This avoids decoding the MP4 later.
            if output_file:
                try:
                    sidecar_data = (
                        self._bright_component_analyzer.write_sidecar(
                            frames,
                            output_file
                        )
                    )

                except Exception as error:
                    self._event_log.add(
                        f"Sidecar analysis failed: {error}",
                        "error"
                    )

            self._capture_manager.cleanup()

        capture_status = {
            "buffer_count": len(
                frames
            ),
            **writer_status
        }

        if sidecar_data is not None:
            capture_status["sidecar"] = sidecar_data

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

    def get_preview_jpeg(self) -> tuple[bytes | None, dict]:
        camera_frame = (
            self._ring_buffer.newest()
        )

        if camera_frame is None:
            return None, {
                "success": False,
                "message": "No preview frame available"
            }

        success, jpeg = cv2.imencode(
            ".jpg",
            camera_frame.frame,
            [
                cv2.IMWRITE_JPEG_QUALITY,
                75
            ]
        )

        if not success:
            return None, {
                "success": False,
                "message": "JPEG encode failed"
            }

        return jpeg.tobytes(), {
            "success": True,
            "sequence_number": camera_frame.sequence_number,
            "timestamp_utc": camera_frame.timestamp_utc,
            "timestamp_monotonic": camera_frame.timestamp_monotonic
        }

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

        trigger_status = (
            self._trigger_manager.get_status()
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
            "metric_history_overwrite_count": metric_status["overwrite_count"],
            "trigger_enabled": trigger_status["enabled"],
            "trigger_state": trigger_status["state"],
            "trigger_max_brightness_delta": trigger_status["max_brightness_delta"],
            "trigger_max_changed_pixel_fraction": trigger_status["max_changed_pixel_fraction"],
            "last_trigger_reason": trigger_status["last_trigger_reason"],
            "last_trigger_time_monotonic": trigger_status["last_trigger_time_monotonic"]
        }

        return status

    def _log_periodic_health(
        self,
        camera_frame: CameraFrame
    ) -> None:
        elapsed_seconds = (
            camera_frame.timestamp_monotonic -
            self._last_health_log_time_monotonic
        )

        if elapsed_seconds < self._config.health_log_interval_seconds:
            return

        self._last_health_log_time_monotonic = (
            camera_frame.timestamp_monotonic
        )

        metric_status = (
            self._metric_history.get_status()
        )
        buffer_status = (
            self._ring_buffer.get_status()
        )

        trigger_status = (
            self._trigger_manager.get_status()
        )

        self._event_log.add(
            (
                f"Health: "
                f"frames={camera_frame.sequence_number}, "
                f"buffer={buffer_status['count']}/{buffer_status['capacity']}, "
                f"metrics={metric_status['count']}/{metric_status['capacity']}, "
                f"metric_overwrites={metric_status['overwrite_count']}, "
                f"trig_bright={trigger_status['max_brightness']}, "
                f"trig_delta={trigger_status['max_brightness_delta']}, "
                f"trig_motion={trigger_status['max_changed_pixel_fraction']}"
            )
        )
            
    def _on_frame_inner(
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

        self._log_periodic_health(
            camera_frame
        )

        if should_sample_metric:
            metric = self._frame_analyzer.analyze(
                camera_frame
            )

            self._metric_history.push(
                metric
            )

            should_fire, trigger_reason = (
                self._trigger_manager.evaluate(
                    metric
                )
            )

            if should_fire:
                success, message, capture_status = (
                    self.capture()
                )

                if success:
                    self._event_log.add(
                        (
                            f"Auto trigger fired: {trigger_reason}; "
                            f"{capture_status['frames_written']} frames, "
                            f"{capture_status['duration_seconds']:.2f} sec, "
                            f"{capture_status.get('output_file', '')}"
                        )
                    )
                else:
                    self._event_log.add(
                        (
                            f"Auto trigger failed: "
                            f"{trigger_reason}; {message}"
                        ),
                        "error"
                    )

            self._last_metric_time_monotonic = (
                camera_frame.timestamp_monotonic
            )

    def _on_frame(
        self,
        camera_frame: CameraFrame
    ) -> None:
        try:
            self._on_frame_inner(
                camera_frame
            )
        except Exception as error:
            error_message = str(
                error
            )

            if error_message != self._last_logged_error:
                self._event_log.add(
                    (
                        f"Buffer failure after frame "
                        f"{camera_frame.sequence_number}: "
                        f"{error_message}"
                    ),
                    "error"
                )

                self._last_logged_error = error_message

            raise        