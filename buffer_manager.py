"""
@file buffer_manager.py

@brief Coordinates CameraReader and RingBuffer.
"""

from cam_config import CamConfig
from camera_reader import CameraReader
from ring_buffer import RingBuffer


class BufferManager:
    """
    @brief Owns camera buffering components.
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

        self._ring_buffer = RingBuffer(
            capacity=self._capacity_frames
        )

        self._camera_reader = CameraReader(
            config,
            on_frame=self._ring_buffer.push
        )

    def start(self) -> tuple[bool, str]:
        success = False
        message = "Buffer already running"

        if not self.is_running():
            self._ring_buffer.clear()

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

            success = True
            message = "Buffer cleared"

        return success, message

    def is_running(self) -> bool:
        return self._camera_reader.is_running()

    def get_status(self) -> dict:
        reader_status = (
            self._camera_reader.get_status()
        )

        buffer_status = (
            self._ring_buffer.get_status()
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
            "newest_sequence_number": buffer_status["newest_sequence_number"]
        }

        return status