"""
@file cam_reader_test.py

@brief Standalone test for CameraReader.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )

from cam_config import CamConfig
from camera_reader import CameraReader


def main() -> int:
    """
    @brief Run CameraReader for ten seconds and print status.

    @return 0 on success, non-zero on failure.
    """

    return_code = 0

    config = CamConfig()

    reader = CameraReader(
        config
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

            status = reader.get_status()

            print(
                f"running={status['running']} "
                f"frames={status['frame_count']} "
                f"fps={status['estimated_fps']:.1f} "
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
            f"failed={status['failed_read_count']} "
            f"last_error={status['last_error']}"
        )

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )
