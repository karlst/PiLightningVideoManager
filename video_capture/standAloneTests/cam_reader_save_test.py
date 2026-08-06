"""
@file cam_reader_save_test.py

@brief Standalone save-frame callback test for CameraReader.
"""

import sys
import time
from pathlib import Path
from threading import Lock

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )

from cam_config import CamConfig
from camera_reader import CameraFrame
from camera_reader import CameraReader


class FrameSaver:
    """
    @brief Saves the first N frames received by callback.
    """

    def __init__(
        self,
        output_dir: Path,
        max_save_count: int
    ) -> None:
        self._output_dir = output_dir
        self._max_save_count = max_save_count
        self._lock = Lock()
        self._save_count = 0

        self._output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def on_frame(
        self,
        camera_frame: CameraFrame
    ) -> None:
        save_this_frame = False
        save_index = 0

        with self._lock:
            if self._save_count < self._max_save_count:
                save_this_frame = True
                save_index = self._save_count
                self._save_count += 1

        if save_this_frame:
            output_file = (
                self._output_dir /
                f"camera_reader_frame_{save_index:04d}.jpg"
            )

            cv2.imwrite(
                str(output_file),
                camera_frame.frame
            )

    def get_save_count(self) -> int:
        save_count = 0

        with self._lock:
            save_count = self._save_count

        return save_count


def main() -> int:
    """
    @brief Run CameraReader with a callback that saves frames.

    @return 0 on success, non-zero on failure.
    """

    return_code = 0

    output_dir = (
        Path.home() /
        "Documents" /
        "videoManager" /
        "camera_reader_save_test"
    )

    config = CamConfig()

    saver = FrameSaver(
        output_dir=output_dir,
        max_save_count=10
    )

    reader = CameraReader(
        config,
        on_frame=saver.on_frame
    )

    success, message = reader.start()

    print(
        message
    )

    if not success:
        return_code = 1
    else:
        for _ in range(5):
            time.sleep(
                1.0
            )

            status = reader.get_status()

            print(
                f"frames={status['frame_count']} "
                f"fps={status['estimated_fps']:.1f} "
                f"saved={saver.get_save_count()} "
                f"failed={status['failed_read_count']} "
                f"last_error={status['last_error']}"
            )

        success, message = reader.stop()

        print(
            message
        )

        status = reader.get_status()

        print(
            f"final_frames={status['frame_count']} "
            f"final_fps={status['estimated_fps']:.1f} "
            f"saved={saver.get_save_count()} "
            f"failed={status['failed_read_count']} "
            f"last_error={status['last_error']}"
        )

        print(
            f"Output directory: {output_dir}"
        )

        if saver.get_save_count() != 10:
            return_code = 2

        if status["failed_read_count"] != 0:
            return_code = 3

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )
