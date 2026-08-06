"""
@file frame_analyzer_metric_history_test.py

@brief Live test for FrameAnalyzer feeding MetricHistory.
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
from cam_config import CamConfig
from camera_reader import CameraFrame
from camera_reader import CameraReader
from frame_analyzer import FrameAnalyzer
from metric_history import MetricHistory


class AnalyzerHistoryCallback:
    """
    @brief Analyzes frames and stores metrics.
    """

    def __init__(
        self,
        analyzer: FrameAnalyzer,
        metric_history: MetricHistory
    ) -> None:
        self._analyzer = analyzer
        self._metric_history = metric_history
        self._analysis_count = 0
        self._last_metric = {}

    def on_frame(
        self,
        camera_frame: CameraFrame
    ) -> None:
        metric = self._analyzer.analyze(
            camera_frame
        )

        self._metric_history.push(
            metric
        )

        self._last_metric = metric
        self._analysis_count += 1

    def get_analysis_count(self) -> int:
        return self._analysis_count

    def get_last_metric(self) -> dict:
        return self._last_metric


def main() -> int:
    return_code = 0

    config = CamConfig()

    analyzer = FrameAnalyzer()

    analyzer.add_plugin(
        BrightnessPlugin(
            average_window_frames=100
        )
    )

    metric_history = MetricHistory(
        capacity=2600
    )

    callback = AnalyzerHistoryCallback(
        analyzer=analyzer,
        metric_history=metric_history
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

            now = time.monotonic()

            reader_status = reader.get_status()
            history_status = metric_history.get_status()
            metric = callback.get_last_metric()

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
                reader_status["elapsed_seconds"] >= warmup_seconds
            ):
                steady_start_time = now
                steady_start_frame_count = (
                    reader_status["frame_count"]
                )

            steady_fps = 0.0

            if steady_start_time is not None:
                steady_elapsed = (
                    now -
                    steady_start_time
                )

                steady_frames = (
                    reader_status["frame_count"] -
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
                f"history_count={history_status['count']} "
                f"history_overwrites={history_status['overwrite_count']} "
                f"interval_fps={interval_fps:.1f} "
                f"steady_fps={steady_fps:.1f} "
                f"mean={metric.get('mean_brightness', 0.0):.2f} "
                f"avg={metric.get('moving_average_brightness', 0.0):.2f} "
                f"delta={metric.get('brightness_delta', 0.0):.2f} "
                f"ram={memory_mb:.1f}MB "
                f"failed={reader_status['failed_read_count']}"
            )

            last_report_time = now
            last_report_frame_count = (
                reader_status["frame_count"]
            )

        success, message = reader.stop()

        print(
            message
        )

        reader_status = reader.get_status()
        history_snapshot = metric_history.snapshot()

        if reader_status["failed_read_count"] != 0:
            return_code = 2

        if callback.get_analysis_count() != reader_status["frame_count"]:
            return_code = 3

        if len(history_snapshot) == 0:
            return_code = 4
        else:
            first_metric = history_snapshot[0]
            last_metric = history_snapshot[-1]

            print(
                "History:"
            )

            print(
                f"first_seq={first_metric['sequence_number']} "
                f"last_seq={last_metric['sequence_number']} "
                f"stored={len(history_snapshot)}"
            )

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )