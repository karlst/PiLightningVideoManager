"""
@file buffer_manager.py

@brief Coordinates CameraReader and RingBuffer.
"""

from cam_config import CamConfig
from camera_reader import CameraReader
from event_log import EventLog
from ring_buffer import RingBuffer


class BufferManager:
    """
    @brief Manages continuous camera buffering.
    """

    def __init__(
        self,
        config: CamConfig,
        event_log: EventLog
    ) -> None:
        self._config = config
        self._event_log = event_log

        capacity = (
            config.frame_rate_fps *
            config.buffer_seconds
        )

        self._ring_buffer = RingBuffer(
            capacity=capacity
        )

        self._camera_reader = CameraReader(
            config,
            on_frame=self._ring_buffer.push
        )

    def start(self) -> tuple[bool, str]:
        success, message = (
            self._camera_reader.start()
        )

        self._event_log.add(
            message
        )

        return success, message

    def stop(self) -> tuple[bool, str]:
        success, message = (
            self._camera_reader.stop()
        )

        self._event_log.add(
            message
        )

        return success, message

    def is_running(self) -> bool:
        return self._camera_reader.is_running()

    def clear(self) -> tuple[bool, str]:
        self._ring_buffer.clear()

        message = "Ring buffer cleared"

        self._event_log.add(
            message
        )

        return True, message

    def capture(self) -> tuple[bool, str]:
        frames = self._ring_buffer.snapshot()

        message = (
            f"STUB: buffer capture requested, "
            f"{len(frames)} frames available"
        )

        self._event_log.add(
            message
        )

        return False, message

    def get_status(self) -> dict:
        reader_status = (
            self._camera_reader.get_status()
        )

        buffer_status = (
            self._ring_buffer.get_status()
        )

        status = {
            "success": True,
            "implemented": True,
            "running": reader_status["running"],
            "reader": reader_status,
            "buffer": buffer_status,
            "message": "Buffer status updated"
        }

        return status