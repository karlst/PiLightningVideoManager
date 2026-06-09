"""
@file frame_analyzer_test.py

@brief Live CameraReader test for FrameAnalyzer.
"""

import os
import psutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )

from brightness_plugin import BrightnessPlugin
from motion_plugin import MotionPlugin
from cam_config import CamConfig
from camera_reader import CameraFrame
from camera_reader import CameraReader
from frame_analyzer import FrameAnalyzer


class AnalyzerCallback:
    """
    @brief Callback wrapper that analyzes incoming frames.
    """

    def __init__(
        self,
        analyzer: FrameAnalyzer
    ) -> None:
        self._analyzer = analyzer
        self._last_result = {}
        self._analysis_count = 0

    def on_frame(
        self,
        camera_frame: CameraFrame
    ) -> None:
        self._last_result = self._analyzer.analyze(
            camera_frame
        )

        self._analysis_count += 1

    def get_last_result(self) -> dict:
        return self._last_result

    def get_analysis_count(self) -> int:
        return self._analysis_count


def main() -> int:
    return_code = 0

    config = CamConfig()

    analyzer = FrameAnalyzer()

    analyzer.add_plugin(
        BrightnessPlugin(
            average_window_frames=100
        )
    )

    analyzer.add_plugin(
        MotionPlugin(
            changed_pixel_threshold=25
        )
    )

    callback = AnalyzerCallback(
        analyzer
    )

    reader = CameraReader(
        config,
        on_frame=callback.on_frame
    )

    process = psutil.Process(
        os.getpid()
    )

    success, message = reader.start()

    print(
        message
    )

    if not success:
        return_code = 1
    else:
        warmup_seconds = 5.0

        steady_start_time = None
        steady_start_frame_count = 0

        last_report_time = time.monotonic()
        last_report_frame_count = 0

        for _ in range(15):
            time.sleep(
                1.0
            )

            reader_status = (
                reader.get_status()
            )

            result = (
                callback.get_last_result()
            )

            now = time.monotonic()

            interval_seconds = (
                now -
                last_report_time
            )

            interval_frames = (
                reader_status["frame_count"] -
                last_report_frame_count
            )

            interval_fps = 0.0

            if interval_seconds > 0.0:
                interval_fps = (
                    interval_frames /
                    interval_seconds
                )

            if (
                steady_start_time is None
                and
                reader_status[
                    "elapsed_seconds"
                ] >= warmup_seconds
            ):
                steady_start_time = now

                steady_start_frame_count = (
                    reader_status[
                        "frame_count"
                    ]
                )

            steady_fps = 0.0

            if (
                steady_start_time
                is not None
            ):
                steady_elapsed = (
                    now -
                    steady_start_time
                )

                steady_frames = (
                    reader_status[
                        "frame_count"
                    ] -
                    steady_start_frame_count
                )

                if steady_elapsed > 0.0:
                    steady_fps = (
                        steady_frames /
                        steady_elapsed
                    )

            memory_mb = (
                process.memory_info().rss /
                (1024 * 1024)
            )

            print(
                f"frames={reader_status['frame_count']} "
                f"analysis={callback.get_analysis_count()} "
                f"interval_fps={interval_fps:.1f} "
                f"steady_fps={steady_fps:.1f} "
                f"mean={result.get('mean_brightness', 0.0):.2f} "
                f"avg={result.get('moving_average_brightness', 0.0):.2f} "
                f"delta={result.get('brightness_delta', 0.0):.2f} "
                f"max={result.get('max_brightness', 0)} "
                f"bright_frac={result.get('bright_pixel_fraction', 0.0):.6f} "
                f"diff_mean={result.get('frame_difference_mean', 0.0):.2f} "
                f"changed_frac={result.get('changed_pixel_fraction', 0.0):.6f} "
                f"ram={memory_mb:.1f}MB "
                f"failed={reader_status['failed_read_count']}"
            )

            last_report_time = now

            last_report_frame_count = (
                reader_status[
                    "frame_count"
                ]
            )

        success, message = (
            reader.stop()
        )

        print(
            message
        )

        reader_status = (
            reader.get_status()
        )

        if (
            reader_status[
                "failed_read_count"
            ] != 0
        ):
            return_code = 2

        if (
            callback.get_analysis_count()
            !=
            reader_status[
                "frame_count"
            ]
        ):
            return_code = 3

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )