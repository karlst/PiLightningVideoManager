"""
@file camera_reader_ring_buffer_test.py

@brief Integration test for CameraReader feeding RingBuffer.
"""

import sys
import time
import os
import psutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )

from cam_config import CamConfig
from camera_reader import CameraReader
from ring_buffer import RingBuffer


def main() -> int:
    return_code = 0

    config = CamConfig()

    capacity_frames = (
        config.frame_rate_fps *
        config.buffer_seconds
    )

    ring_buffer = RingBuffer(
        capacity=capacity_frames
    )

    reader = CameraReader(
        config,
        on_frame=ring_buffer.push
    )

    success, message = reader.start()

    print(
        message
    )

    if not success:
        return_code = 1
    else:

        process = psutil.Process(
            os.getpid()
        )

        for _ in range(10):
            time.sleep(
                1.0
            )

            

            reader_status = reader.get_status()
            buffer_status = ring_buffer.get_status()

            rss_mb = (
                process.memory_info().rss /
                (1024 * 1024)
            )

            print(
                f"reader_frames={reader_status['frame_count']} "
                f"buffer_count={buffer_status['count']} "
                f"memory_mb={rss_mb:.1f}"
            )

            print(
                f"reader_frames={reader_status['frame_count']} "
                f"reader_fps={reader_status['estimated_fps']:.1f} "
                f"buffer_count={buffer_status['count']} "
                f"total_pushed={buffer_status['total_pushed']} "
                f"overwrites={buffer_status['overwrite_count']} "
                f"oldest_seq={buffer_status['oldest_sequence_number']} "
                f"newest_seq={buffer_status['newest_sequence_number']} "
                f"failed={reader_status['failed_read_count']}"
            )

        success, message = reader.stop()

        print(
            message
        )

        reader_status = reader.get_status()
        buffer_status = ring_buffer.get_status()

        print(
            "Final:"
        )

        print(
            f"reader_frames={reader_status['frame_count']} "
            f"reader_fps={reader_status['estimated_fps']:.1f} "
            f"buffer_capacity={buffer_status['capacity']} "
            f"buffer_count={buffer_status['count']} "
            f"total_pushed={buffer_status['total_pushed']} "
            f"overwrites={buffer_status['overwrite_count']} "
            f"oldest_seq={buffer_status['oldest_sequence_number']} "
            f"newest_seq={buffer_status['newest_sequence_number']} "
            f"failed={reader_status['failed_read_count']} "
            f"last_error={reader_status['last_error']}"
        )

        if buffer_status["count"] != capacity_frames:
            return_code = 2

        if buffer_status["total_pushed"] != reader_status["frame_count"]:
            return_code = 3

        if buffer_status["newest_sequence_number"] != reader_status["frame_count"]:
            return_code = 4

        if reader_status["failed_read_count"] != 0:
            return_code = 5

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )