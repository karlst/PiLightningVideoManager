"""
@file buffer_manager.py

@brief Coordinates the live camera capture pipeline.

BufferManager is the central coordinator for camera capture on the Pi. It
receives every frame from CameraReader, keeps recent frames in the ring
buffer, calculates the metrics used for candidate detection, asks
TriggerManager whether a candidate has been found, and saves the buffered
frames as an MP4 plus JSON sidecar when a capture is triggered. It also
provides preview images, status information, and sampled metrics used by the
web interface.
"""

from queue import Queue
from threading import Lock
from threading import Thread

import cv2

from video_capture.brightness_plugin import BrightnessPlugin
from video_capture.cam_config import CamConfig
from video_capture.cam_config import build_search_bounding_box
from video_capture.camera_reader import CameraFrame
from video_capture.camera_reader import CameraReader
from video_capture.clip_writer import ClipWriter
from video_capture.event_log import EventLog
from video_capture.frame_analyzer import FrameAnalyzer
from video_capture.metric_history import MetricHistory
from video_capture.motion_plugin import MotionPlugin
from video_capture.ring_buffer import RingBuffer
from video_capture.trigger_manager import TriggerManager
from video_capture.capture_manager import CaptureManager
from video_capture.sidecar_writer import SidecarWriter
from common.candidate_config import CANDIDATE_CONFIG


# ## Owns camera buffering, analysis, trigger, and capture components.
class BufferManager:
    """
    @brief Owns camera buffering, analysis, trigger, and capture components.
    """

    # ## Initialize camera buffering, metrics, triggering, and capture helpers.
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

        self._sidecar_writer = SidecarWriter()

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

        # Automatic capture files are written outside the CameraReader thread.
        # The reader callback only takes a ring-buffer snapshot and queues it,
        # so FFmpeg encoding and sidecar analysis cannot block camera.read().
        # One worker serializes all automatic writes. The write lock also
        # protects ClipWriter/SidecarWriter if a synchronous manual capture
        # happens while an automatic capture is being written.
        self._capture_write_lock = Lock()
        self._capture_queue = Queue()
        self._capture_writer_thread = Thread(
            target=self._capture_writer_loop,
            name="CaptureWriter",
            daemon=True
        )
        self._capture_writer_thread.start()

        self._last_metric_time_monotonic: float = 0.0
        self._last_health_log_time_monotonic: float = 0.0
        self._last_logged_error: str = ""
        self._previous_trigger_gray_frame = None

        # Auto-trigger capture state.
        #
        # IDLE:
        #     no auto-trigger is waiting.
        #
        # WAITING_FOR_POST:
        #     trigger frame has been recorded, but capture is intentionally
        #     delayed until post_trigger_seconds of later frames are buffered.
        self._capture_state: str = "IDLE"
        self._pending_trigger: dict | None = None

        # Lightweight trigger-only brightness state.
        #
        # This path runs on every frame. It intentionally avoids the heavier
        # graph/sidecar analysis plugins so lightning strokes are not missed
        # by the slower metric-history sampling interval.
        self._previous_trigger_mean_brightness: float | None = None

    # ## Start the camera reader and clear existing runtime buffers.
    def start(self) -> tuple[bool, str]:
        success = False
        message = "Buffer already running"

        if not self.is_running():
            self._ring_buffer.clear()
            self._metric_history.clear()
            self._clear_pending_trigger()
            self._reset_live_analysis_state()

            success, message = (
                self._camera_reader.start()
            )

        if success:
            self._event_log.add(
                "CameraReader started",
                event_type="system",
                summary="Camera started"
            )
        else:
            self._event_log.add(
                f"CameraReader start failed: {message}",
                "error",
                event_type="error",
                summary="Camera start failed"
            )

        return success, message

    # ## Stop the camera reader thread.
    def stop(self) -> tuple[bool, str]:
        success, message = (
            self._camera_reader.stop()
        )

        return success, message

    # ## Clear buffered frames and metrics when the camera is stopped.
    def clear(self) -> tuple[bool, str]:
        success = False
        message = "Buffer is running; stop before clearing"

        if not self.is_running():
            self._ring_buffer.clear()
            self._metric_history.clear()
            self._clear_pending_trigger()
            self._reset_live_analysis_state()

            success = True
            message = "Buffer cleared"

        return success, message

    # ## Capture the current ring buffer and write MP4 plus analysis sidecar.
    def capture(
        self,
        trigger_type: str = "manual",
        trigger_display: str = "Manual",
        trigger_reason: str = "Manual capture",
        trigger_sequence_number: int | None = None,
        trigger_timestamp_utc: str = "",
        trigger_time_monotonic: float | None = None,
        candidate_config: dict | None = None
    ) -> tuple[bool, str, dict]:
        frames = (
            self._ring_buffer.snapshot()
        )

        if candidate_config is None:
            candidate_config = (
                self._trigger_manager.get_candidate_config_dict()
            )

        # Manual captures use the newest buffered frame as their practical
        # trigger reference. Auto captures pass the original trigger primitive
        # values recorded when the threshold was crossed.
        if len(frames) > 0 and trigger_sequence_number is None:
            newest_frame = frames[-1]
            trigger_sequence_number = newest_frame.sequence_number
            trigger_timestamp_utc = newest_frame.timestamp_utc
            trigger_time_monotonic = newest_frame.timestamp_monotonic

        return self._write_capture_frames(
            frames=frames,
            trigger_type=trigger_type,
            trigger_display=trigger_display,
            trigger_reason=trigger_reason,
            trigger_sequence_number=trigger_sequence_number,
            trigger_timestamp_utc=trigger_timestamp_utc,
            trigger_time_monotonic=trigger_time_monotonic,
            candidate_config=candidate_config
        )

    # ## Write one fixed frame snapshot to MP4 plus sidecar.
    def _write_capture_frames(
        self,
        frames: list[CameraFrame],
        trigger_type: str,
        trigger_display: str,
        trigger_reason: str,
        trigger_sequence_number: int | None,
        trigger_timestamp_utc: str,
        trigger_time_monotonic: float | None,
        candidate_config: dict
    ) -> tuple[bool, str, dict]:
        # Serialize ClipWriter and SidecarWriter use across the automatic
        # writer thread and any synchronous manual-capture caller.
        with self._capture_write_lock:
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

                sidecar_metadata = self._create_sidecar_metadata(
                    frames=frames,
                    writer_status=writer_status,
                    trigger_type=trigger_type,
                    trigger_display=trigger_display,
                    trigger_reason=trigger_reason,
                    trigger_sequence_number=trigger_sequence_number,
                    trigger_timestamp_utc=trigger_timestamp_utc,
                    trigger_time_monotonic=trigger_time_monotonic,
                    candidate_config=candidate_config
                )

                # Analyze the raw captured frames directly and write the JSON
                # sidecar next to the MP4. This now runs on the capture writer
                # thread for automatic captures, not on CameraReader.
                if output_file:
                    try:
                        sidecar_data = (
                            self._sidecar_writer.write_sidecar(
                                frames,
                                output_file,
                                sidecar_metadata
                            )
                        )

                    except Exception as error:
                        self._event_log.add(
                            f"Sidecar analysis failed: {error}",
                            "error",
                            event_type="error",
                            summary="Sidecar analysis failed"
                        )

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

    # ## Write queued automatic captures without blocking CameraReader.
    def _capture_writer_loop(
        self
    ) -> None:
        while True:
            capture_job = self._capture_queue.get()

            try:
                success, message, capture_status = (
                    self._write_capture_frames(
                        frames=capture_job["frames"],
                        trigger_type=capture_job["trigger_type"],
                        trigger_display=capture_job["trigger_display"],
                        trigger_reason=capture_job["trigger_reason"],
                        trigger_sequence_number=capture_job[
                            "trigger_sequence_number"
                        ],
                        trigger_timestamp_utc=capture_job[
                            "trigger_timestamp_utc"
                        ],
                        trigger_time_monotonic=capture_job[
                            "trigger_time_monotonic"
                        ],
                        candidate_config=capture_job[
                            "candidate_config"
                        ]
                    )
                )

                if success:
                    trigger_frame_text = (
                        self._get_capture_trigger_frame_text(
                            capture_status
                        )
                    )

                    self._event_log.add(
                        (
                            f"Auto trigger captured: "
                            f"{capture_job['trigger_reason']}; "
                            f"{capture_status['frames_written']} frames, "
                            f"{capture_status['duration_seconds']:.2f} sec, "
                            f"{trigger_frame_text}, "
                            f"{capture_status.get('output_file', '')}"
                        ),
                        event_type="trigger",
                        summary=(
                            f"Auto trigger captured, "
                            f"{capture_status['frames_written']} frames"
                        )
                    )
                else:
                    self._event_log.add(
                        (
                            f"Auto trigger failed: "
                            f"{capture_job['trigger_reason']}; "
                            f"{message}"
                        ),
                        "error",
                        event_type="error",
                        summary="Auto trigger failed"
                    )

            except Exception as error:
                self._event_log.add(
                    (
                        f"Auto capture writer failure: "
                        f"{capture_job.get('trigger_reason', '')}; "
                        f"{error}"
                    ),
                    "error",
                    event_type="error",
                    summary="Auto capture writer failure"
                )

            finally:
                self._capture_queue.task_done()

    # ## Encode the newest buffered frame as a JPEG preview image.
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

    # ## Return whether the camera reader is running.
    def is_running(self) -> bool:
        return self._camera_reader.is_running()

    # ## Return sampled metric history for graphing.
    def get_metrics_history(self) -> list[dict]:
        return self._metric_history.snapshot()

    # ## Return combined camera, buffer, metrics, and trigger status.
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
            "last_trigger_reason": trigger_status["last_trigger_reason"],
            "last_trigger_time_monotonic": trigger_status["last_trigger_time_monotonic"],
            "capture_state": self._capture_state,
            "pending_trigger": self._pending_trigger is not None
        }

        return status

    # ## Write a periodic health line to the event log.
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
                f"candidate_delta_threshold="
                f"{trigger_status['candidate_config']['candidate_brightness_delta_threshold']}"
            ),
            event_type="health",
            summary=(
                f"Health frames={camera_frame.sequence_number} "
                f"buffer={buffer_status['count']}/{buffer_status['capacity']}"
            )
        )

    # ## Process one frame from CameraReader.
    def _on_frame_inner(
        self,
        camera_frame: CameraFrame
    ) -> None:
        self._ring_buffer.push(
            camera_frame
        )

        self._log_periodic_health(
            camera_frame
        )

        captured_pending_trigger = self._capture_pending_trigger_if_ready(
            camera_frame
        )

        # Run the lightweight trigger metric on every frame. Graph history
        # sampling remains slower, but trigger detection no longer waits for
        # metric_history_sample_seconds.
        trigger_metric = self._analyze_trigger_frame(
            camera_frame
        )

        if (
            self._capture_state == "IDLE" and
            not captured_pending_trigger
        ):
            should_fire, trigger_reason = (
                self._trigger_manager.evaluate(
                    trigger_metric,
                    camera_frame.timestamp_monotonic
                )
            )

            if should_fire:
                self._arm_pending_trigger(
                    trigger_reason=trigger_reason,
                    trigger_frame=camera_frame
                )

        should_sample_metric = (
            (
                camera_frame.timestamp_monotonic -
                self._last_metric_time_monotonic
            ) >= self._config.metric_history_sample_seconds
        )

        if should_sample_metric:
            # Full plugin analysis is for graph/history display only. It is
            # intentionally not used to decide lightning triggers.
            metric = self._frame_analyzer.analyze(
                camera_frame
            )

            self._metric_history.push(
                metric
            )

            self._last_metric_time_monotonic = (
                camera_frame.timestamp_monotonic
            )

    # ## Analyze one frame using the cheap every-frame trigger metric.
    # ## Analyze one frame using the cheap every-frame trigger metric.
    def _analyze_trigger_frame(
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

        brightness_delta_adjacent = 0.0
        bright_pixel_fraction = 0.0

        if self._previous_trigger_mean_brightness is not None:
            brightness_delta_adjacent = (
                mean_brightness -
                self._previous_trigger_mean_brightness
            )

        if self._previous_trigger_gray_frame is not None:
            candidate_config = (
                self._trigger_manager.get_candidate_config()
            )

            positive_delta = cv2.subtract(
                gray_frame,
                self._previous_trigger_gray_frame
            )

            threshold_mask = cv2.compare(
                positive_delta,
                candidate_config.
                candidate_bright_pixel_delta_threshold,
                cv2.CMP_GE
            )

            bright_pixel_count = (
                cv2.countNonZero(
                    threshold_mask
                )
            )

            bright_pixel_fraction = (
                float(bright_pixel_count) /
                float(positive_delta.size)
            )

        self._previous_trigger_mean_brightness = (
            mean_brightness
        )

        self._previous_trigger_gray_frame = (
            gray_frame
        )

        metric = {
            "sequence_number":
                camera_frame.sequence_number,
            "timestamp_utc":
                camera_frame.timestamp_utc,
            "timestamp_monotonic":
                camera_frame.timestamp_monotonic,
            "mean_brightness":
                mean_brightness,
            "brightness_delta_adjacent":
                brightness_delta_adjacent,

            # Legacy key retained for existing graph/status code.
            "brightness_delta":
                brightness_delta_adjacent,

            "bright_pixel_fraction":
                bright_pixel_fraction
        }

        return metric

    # ## Remember an auto-trigger and wait for post-trigger frames.
    def _arm_pending_trigger(
        self,
        trigger_reason: str,
        trigger_frame: CameraFrame
    ) -> None:
        trigger_type, trigger_display = (
            self._get_trigger_identity(
                trigger_reason
            )
        )

        # Record only primitive values. Do not keep the CameraFrame object;
        # later frames will continue arriving and capture should use this
        # exact original sequence number, not the eventual newest frame.
        self._pending_trigger = {
            "trigger_type": trigger_type,
            "trigger_display": trigger_display,
            "trigger_reason": trigger_reason,
            "trigger_sequence_number": trigger_frame.sequence_number,
            "trigger_timestamp_utc": trigger_frame.timestamp_utc,
            "trigger_time_monotonic": trigger_frame.timestamp_monotonic,
            "armed_time_monotonic": trigger_frame.timestamp_monotonic,
            "candidate_config":
                self._trigger_manager.get_candidate_config_dict()
        }

        self._capture_state = "WAITING_FOR_POST"

        self._event_log.add(
            (
                f"Auto trigger armed: {trigger_reason}; "
                f"post={self._config.post_trigger_seconds:.2f} sec, "
                f"frame={trigger_frame.sequence_number}"
            ),
            event_type="trigger",
            summary=(
                f"Auto trigger armed, "
                f"frame {trigger_frame.sequence_number}"
            )
        )

    # ## Queue a pending auto-trigger after post-trigger time has elapsed.
    def _capture_pending_trigger_if_ready(
        self,
        camera_frame: CameraFrame
    ) -> bool:
        captured_pending_trigger = False

        if (
            self._capture_state == "WAITING_FOR_POST" and
            self._pending_trigger is not None
        ):
            trigger_time_monotonic = float(
                self._pending_trigger[
                    "trigger_time_monotonic"
                ]
            )

            elapsed_seconds = (
                camera_frame.timestamp_monotonic -
                trigger_time_monotonic
            )

            if elapsed_seconds >= self._config.post_trigger_seconds:
                pending_trigger = dict(
                    self._pending_trigger
                )

                # Snapshot while still on the CameraReader thread. This copies
                # only the list of CameraFrame references; RingBuffer does not
                # mutate frames that have already been pushed. The queued list
                # therefore owns the exact capture frames while the live ring
                # buffer continues to overwrite its own references.
                frames = (
                    self._ring_buffer.snapshot()
                )

                capture_job = {
                    "frames": frames,
                    "trigger_type": pending_trigger["trigger_type"],
                    "trigger_display": pending_trigger["trigger_display"],
                    "trigger_reason": pending_trigger["trigger_reason"],
                    "trigger_sequence_number": pending_trigger[
                        "trigger_sequence_number"
                    ],
                    "trigger_timestamp_utc": pending_trigger[
                        "trigger_timestamp_utc"
                    ],
                    "trigger_time_monotonic": pending_trigger[
                        "trigger_time_monotonic"
                    ],
                    "candidate_config": pending_trigger[
                        "candidate_config"
                    ]
                }

                self._pending_trigger = None
                self._capture_state = "IDLE"
                captured_pending_trigger = True

                # Queue insertion is in-memory and returns immediately. The
                # expensive FFmpeg and sidecar work runs on CaptureWriter.
                self._capture_queue.put_nowait(
                    capture_job
                )

                # Preserve the old post-capture live-analysis semantics for
                # the very next camera frame, but do the reset immediately
                # after snapshotting rather than after file writing finishes.
                self._reset_live_analysis_state()
                self._last_metric_time_monotonic = (
                    camera_frame.timestamp_monotonic
                )

        return captured_pending_trigger

    # ## Build the portable clip-level sidecar metadata.
    def _create_sidecar_metadata(
        self,
        frames: list[CameraFrame],
        writer_status: dict,
        trigger_type: str,
        trigger_display: str,
        trigger_reason: str,
        trigger_sequence_number: int | None,
        trigger_timestamp_utc: str,
        trigger_time_monotonic: float | None,
        candidate_config: dict
    ) -> dict:
        capture_start_utc = ""
        capture_end_utc = ""
        capture_duration_ms = 0.0

        trigger_frame_index = None
        trigger_offset_ms = None

        if len(frames) > 0:
            first_frame = frames[0]
            last_frame = frames[-1]

            capture_start_utc = first_frame.timestamp_utc
            capture_end_utc = last_frame.timestamp_utc
            capture_duration_ms = round(
                (
                    last_frame.timestamp_monotonic -
                    first_frame.timestamp_monotonic
                ) * 1000.0,
                3
            )

        if trigger_sequence_number is not None:
            trigger_frame_index = self._get_frame_index(
                frames,
                trigger_sequence_number
            )

            if (
                trigger_time_monotonic is not None and
                len(frames) > 0
            ):
                trigger_offset_ms = round(
                    (
                        trigger_time_monotonic -
                        frames[0].timestamp_monotonic
                    ) * 1000.0,
                    3
                )

        search_bounding_box = (
            build_search_bounding_box(
                latitude_degrees=
                    self._config.
                    camera_latitude_degrees,

                longitude_degrees=
                    self._config.
                    camera_longitude_degrees,

                bearing_degrees=
                    self._config.
                    camera_bearing_degrees,

                hfov_degrees=
                    self._config.
                    camera_hfov_degrees,

                minimum_range_miles=
                    self._config.
                    search_minimum_range_miles,

                maximum_range_miles=
                    self._config.
                    search_maximum_range_miles,
            )
        )

        return {
            "application": {
                "name": "Pi Camera Capture",
                "version": self._config.app_version,
                "start_utc": self._config.application_start_utc
            },
            "camera": {
                "site_name":
                    self._config.camera_site_name,

                "name":
                    self._config.camera_name,

                "type":
                    self._config.camera_type,
                "input_format": self._config.input_format,
                "frame_width_pixels": self._config.frame_width_pixels,
                "frame_height_pixels": self._config.frame_height_pixels,
                "frame_rate_fps": self._config.frame_rate_fps,
                "latitude_degrees": self._config.camera_latitude_degrees,
                "longitude_degrees": self._config.camera_longitude_degrees,
                "bearing_degrees": self._config.camera_bearing_degrees,
                "hfov_degrees": self._config.camera_hfov_degrees,
                "vfov_degrees":
                    self._config.camera_vfov_degrees,

                "search_bounding_box":
                    search_bounding_box
            },

            "search_bounding_box":
                search_bounding_box,

            "capture": {
                "saved_utc": writer_status.get(
                    "saved_utc",
                    ""
                ),
                "start_utc": capture_start_utc,
                "end_utc": capture_end_utc,
                "duration_ms": capture_duration_ms,
                "frame_count": len(frames)
            },
            "candidate": {
                "trigger_type": trigger_type,
                "trigger_display": trigger_display,
                "trigger_reason": trigger_reason,
                "trigger_utc": trigger_timestamp_utc,
                "trigger_sequence_number": trigger_sequence_number,
                "trigger_frame_index": trigger_frame_index,
                "trigger_offset_ms": trigger_offset_ms,
                "config": candidate_config
            }
        }

    # ## Find a camera sequence number within the saved capture frame list.
    def _get_frame_index(
        self,
        frames: list[CameraFrame],
        sequence_number: int
    ) -> int | None:
        frame_index = None

        for index, camera_frame in enumerate(
            frames
        ):
            if camera_frame.sequence_number == sequence_number:
                frame_index = index
                break

        return frame_index

    # ## Convert trigger reason text into stable sidecar labels.
    # ## Convert trigger reason text into stable sidecar labels.
    def _get_trigger_identity(
        self,
        trigger_reason: str
    ) -> tuple[str, str]:
        trigger_type = "unknown"
        trigger_display = "Auto"

        reason_lower = trigger_reason.lower()

        if "brightness delta trigger" in reason_lower:
            trigger_type = "brightness_delta"
            trigger_display = "Δ Bright"

        elif "bright pixel trigger" in reason_lower:
            trigger_type = "bright_pixel"
            trigger_display = "Bright Pixels"

        elif "brightness trigger" in reason_lower:
            trigger_type = "brightness"
            trigger_display = "Brightness"

        return trigger_type, trigger_display

    # ## Produce event-log text for the trigger frame stored in a sidecar.
    def _get_capture_trigger_frame_text(
        self,
        capture_status: dict
    ) -> str:
        text = "trigger frame unknown"

        sidecar = capture_status.get(
            "sidecar",
            {}
        )

        candidate = sidecar.get(
            "candidate",
            {}
        )

        capture = sidecar.get(
            "capture",
            {}
        )

        trigger_frame_index = candidate.get(
            "trigger_frame_index"
        )

        frame_count = capture.get(
            "frame_count"
        )

        if (
            trigger_frame_index is not None and
            frame_count is not None
        ):
            text = (
                f"trigger frame "
                f"{int(trigger_frame_index) + 1}/{frame_count}"
            )

        return text

    # ## Reset live analyzer state after startup, clear, or capture.
    def _reset_live_analysis_state(self) -> None:
        # Rebuild graph/history plugins so stale moving averages and previous
        # frames cannot create artificial brightness or motion deltas after a
        # capture completes.
        self._frame_analyzer = FrameAnalyzer()

        self._frame_analyzer.add_plugin(
            BrightnessPlugin(
                average_window_frames=self._config.brightness_average_frames
            )
        )

        self._frame_analyzer.add_plugin(
            MotionPlugin(
                changed_pixel_threshold=(
                    self._config.motion_changed_pixel_threshold
                )
            )
        )

        # Reset the every-frame trigger baseline. The next frame establishes a
        # fresh adjacent-frame reference and cannot immediately retrigger.
        self._previous_trigger_mean_brightness = None
        self._previous_trigger_gray_frame = None

    # ## Reset pending auto-trigger state.
    def _clear_pending_trigger(self) -> None:
        self._capture_state = "IDLE"
        self._pending_trigger = None

    # ## Catch and log frame-processing errors without spamming repeats.
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
                    "error",
                    event_type="error",
                    summary=f"Buffer failure frame {camera_frame.sequence_number}"
                )

                self._last_logged_error = error_message

            raise
