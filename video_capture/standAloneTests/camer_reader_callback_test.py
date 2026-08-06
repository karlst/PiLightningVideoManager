"""
@file camera_reader_callback_test.py

@brief Standalone callback test for CameraReader.
"""

import sys
import time
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )

from cam_config import CamConfig
from camera_reader import CameraFrame
from camera_reader import CameraReader


class FrameCounter:
    """
    @brief Thread-safe frame callback counter.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._callback_count = 0
        self._last_sequence_number = 0
        self._sequence_gap_count = 0

    def on_frame(
        self,
        camera_frame: CameraFrame
    ) -> None:
        with self._lock:
            expected_sequence_number = (
                self._last_sequence_number + 1
            )

            if (
                self._last_sequence_number > 0
                and camera_frame.sequence_number != expected_sequence_number
            ):
                self._sequence_gap_count += 1

            self._callback_count += 1
            self._last_sequence_number = camera_frame.sequence_number

    def get_status(self) -> dict:
        with self._lock:
            status = {
                "callback_count": self._callback_count,
                "last_sequence_number": self._last_sequence_number,
                "sequence_gap_count": self._sequence_gap_count
            }

        return status


def main() -> int:
    """
    @brief Run CameraReader with callback counting.

    @return 0 on success, non-zero on failure.
    """

    return_code = 0

    config = CamConfig()

    counter = FrameCounter()

    reader = CameraReader(
        config,
        on_frame=counter.on_frame
    )

    success, message = reader.start()

    print(
        message
    )

    if not success:
        return_code = 1
    else:
        for _ in range(10):
            time.sleep(
                1.0
            )

            reader_status = reader.get_status()
            callback_status = counter.get_status()

            print(
                f"reader_frames={reader_status['frame_count']} "
                f"callbacks={callback_status['callback_count']} "
                f"last_seq={callback_status['last_sequence_number']} "
                f"gaps={callback_status['sequence_gap_count']} "
                f"fps={reader_status['estimated_fps']:.1f} "
                f"failed={reader_status['failed_read_count']}"
            )

        success, message = reader.stop()

        print(
            message
        )

        reader_status = reader.get_status()
        callback_status = counter.get_status()

        print(
            f"final_reader_frames={reader_status['frame_count']} "
            f"final_callbacks={callback_status['callback_count']} "
            f"final_last_seq={callback_status['last_sequence_number']} "
            f"final_gaps={callback_status['sequence_gap_count']} "
            f"final_fps={reader_status['estimated_fps']:.1f} "
            f"failed={reader_status['failed_read_count']} "
            f"last_error={reader_status['last_error']}"
        )

        if (
            reader_status["frame_count"]
            != callback_status["callback_count"]
        ):
            return_code = 2

        if callback_status["sequence_gap_count"] != 0:
            return_code = 3

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )
