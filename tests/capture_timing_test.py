"""
Standalone Pi capture timing / forced-capture stress test.

Run this only after stopping pcm.service so this process can own the camera.
psf.service should remain running during the Step-4 test.

The harness subclasses the production BufferManager. It records frame-arrival
gaps and callback duration while forcing automatic captures through the same
pending-trigger -> CaptureWriter -> FFmpeg -> sidecar path used in production.

Production camera_reader.py and buffer_manager.py are not modified.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import statistics
import time

from video_capture.buffer_manager import BufferManager
from video_capture.cam_config import CamConfig
from video_capture.camera_reader import CameraFrame
from video_capture.capture_manager import CaptureManager
from video_capture.event_log import EventLog
from video_capture.trigger_manager import TriggerManager


DEFAULT_TRIGGER_GAPS = (
    5.0,
    10.0,
    12.0,
    30.0,
    11.0,
)


class TimingBufferManager(BufferManager):
    """Production BufferManager with test-only timing and forced triggers."""

    def __init__(
        self,
        config: CamConfig,
        trigger_manager: TriggerManager,
        event_log: EventLog,
        capture_manager: CaptureManager,
        trigger_gaps: tuple[float, ...],
        run_id: str,
    ) -> None:
        self._timing_run_id = str(
            run_id
        )

        self._timing_trigger_gaps = tuple(
            float(value)
            for value in trigger_gaps
        )

        if (
            not self._timing_trigger_gaps
            or any(
                value <= 0.0
                for value in self._timing_trigger_gaps
            )
        ):
            raise ValueError(
                "trigger_gaps must contain positive values"
            )

        self._timing_trigger_count = 0
        self._timing_trigger_gap_index = 0
        self._timing_next_trigger_seconds = (
            self._timing_trigger_gaps[0]
        )
        self._timing_first_frame_monotonic: float | None = None
        self._timing_previous_frame_monotonic: float | None = None
        self._timing_rows: list[dict] = []

        # Filled by the overridden _capture_pending_trigger_if_ready() on the
        # exact CameraReader callback where post-trigger acquisition completes.
        self._timing_pending_metrics: dict[str, float] | None = None

        super().__init__(
            config,
            trigger_manager,
            event_log,
            capture_manager,
        )

    def _on_frame(
        self,
        camera_frame: CameraFrame,
    ) -> None:
        if self._timing_first_frame_monotonic is None:
            self._timing_first_frame_monotonic = (
                camera_frame.timestamp_monotonic
            )

        elapsed_seconds = (
            camera_frame.timestamp_monotonic
            - self._timing_first_frame_monotonic
        )

        frame_gap_ms = None

        if self._timing_previous_frame_monotonic is not None:
            frame_gap_ms = (
                camera_frame.timestamp_monotonic
                - self._timing_previous_frame_monotonic
            ) * 1000.0

        forced_trigger = False

        if (
            self._capture_state == "IDLE"
            and elapsed_seconds
            >= self._timing_next_trigger_seconds
        ):
            scheduled_seconds = (
                self._timing_next_trigger_seconds
            )

            self._arm_pending_trigger(
                trigger_reason=(
                    "Brightness delta trigger: "
                    f"timing test forced capture at {scheduled_seconds:.1f}s"
                ),
                trigger_frame=camera_frame,
            )

            self._timing_trigger_count += 1
            forced_trigger = True

            self._timing_trigger_gap_index = (
                self._timing_trigger_gap_index + 1
            ) % len(
                self._timing_trigger_gaps
            )

            self._timing_next_trigger_seconds += (
                self._timing_trigger_gaps[
                    self._timing_trigger_gap_index
                ]
            )

        self._timing_pending_metrics = None

        callback_start = time.perf_counter()

        super()._on_frame(
            camera_frame
        )

        callback_ms = (
            time.perf_counter()
            - callback_start
        ) * 1000.0

        pending_metrics = (
            self._timing_pending_metrics
            or {}
        )

        self._timing_rows.append(
            {
                "sequence_number":
                    camera_frame.sequence_number,
                "timestamp_utc":
                    camera_frame.timestamp_utc,
                "elapsed_seconds":
                    round(
                        elapsed_seconds,
                        6,
                    ),
                "frame_gap_ms":
                    (
                        ""
                        if frame_gap_ms is None
                        else round(
                            frame_gap_ms,
                            6,
                        )
                    ),
                "callback_ms":
                    round(
                        callback_ms,
                        6,
                    ),
                "pending_total_ms":
                    (
                        ""
                        if "pending_total_ms" not in pending_metrics
                        else round(
                            pending_metrics["pending_total_ms"],
                            6,
                        )
                    ),
                "snapshot_ms":
                    (
                        ""
                        if "snapshot_ms" not in pending_metrics
                        else round(
                            pending_metrics["snapshot_ms"],
                            6,
                        )
                    ),
                "job_build_ms":
                    (
                        ""
                        if "job_build_ms" not in pending_metrics
                        else round(
                            pending_metrics["job_build_ms"],
                            6,
                        )
                    ),
                "queue_ms":
                    (
                        ""
                        if "queue_ms" not in pending_metrics
                        else round(
                            pending_metrics["queue_ms"],
                            6,
                        )
                    ),
                "reset_ms":
                    (
                        ""
                        if "reset_ms" not in pending_metrics
                        else round(
                            pending_metrics["reset_ms"],
                            6,
                        )
                    ),
                "forced_trigger":
                    int(
                        forced_trigger
                    ),
            }
        )

        self._timing_previous_frame_monotonic = (
            camera_frame.timestamp_monotonic
        )

    def _capture_pending_trigger_if_ready(
        self,
        camera_frame: CameraFrame,
    ) -> bool:
        """Instrument the production post-trigger handoff without changing it."""
        captured_pending_trigger = False

        if (
            self._capture_state == "WAITING_FOR_POST"
            and self._pending_trigger is not None
        ):
            trigger_time_monotonic = float(
                self._pending_trigger["trigger_time_monotonic"]
            )

            elapsed_seconds = (
                camera_frame.timestamp_monotonic
                - trigger_time_monotonic
            )

            if elapsed_seconds >= self._config.post_trigger_seconds:
                total_start = time.perf_counter()

                pending_trigger = dict(
                    self._pending_trigger
                )

                snapshot_start = time.perf_counter()

                frames = (
                    self._ring_buffer.snapshot()
                )

                snapshot_ms = (
                    time.perf_counter()
                    - snapshot_start
                ) * 1000.0

                job_build_start = time.perf_counter()

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
                    ],
                }

                self._pending_trigger = None
                self._capture_state = "IDLE"
                captured_pending_trigger = True

                job_build_ms = (
                    time.perf_counter()
                    - job_build_start
                ) * 1000.0

                queue_start = time.perf_counter()

                self._capture_queue.put_nowait(
                    capture_job
                )

                queue_ms = (
                    time.perf_counter()
                    - queue_start
                ) * 1000.0

                reset_start = time.perf_counter()

                self._reset_live_analysis_state()
                self._last_metric_time_monotonic = (
                    camera_frame.timestamp_monotonic
                )

                reset_ms = (
                    time.perf_counter()
                    - reset_start
                ) * 1000.0

                pending_total_ms = (
                    time.perf_counter()
                    - total_start
                ) * 1000.0

                self._timing_pending_metrics = {
                    "pending_total_ms": pending_total_ms,
                    "snapshot_ms": snapshot_ms,
                    "job_build_ms": job_build_ms,
                    "queue_ms": queue_ms,
                    "reset_ms": reset_ms,
                }

        return captured_pending_trigger

    def _write_capture_frames(
        self,
        *args,
        **kwargs,
    ):
        """Use production writing, then rename timing-test pairs to capture_*.

        Production ClipWriter currently writes trigger_*.mp4.  PSF intentionally
        scans only capture_*.mp4, so the timing harness renames its completed
        MP4/JSON pair immediately after the normal production write finishes.
        Production BufferManager and ClipWriter remain untouched.
        """
        success, message, capture_status = (
            super()._write_capture_frames(
                *args,
                **kwargs,
            )
        )

        if not success:
            return (
                success,
                message,
                capture_status,
            )

        output_file = capture_status.get(
            "output_file"
        )

        if not output_file:
            return (
                success,
                message,
                capture_status,
            )

        video_path = Path(
            output_file
        )

        if not video_path.name.startswith(
            "trigger_"
        ):
            return (
                success,
                message,
                capture_status,
            )

        renamed_video_path = (
            video_path.with_name(
                "capture_" +
                video_path.name[
                    len("trigger_"):
                ]
            )
        )

        sidecar_path = (
            video_path.with_suffix(
                ".json"
            )
        )

        renamed_sidecar_path = (
            renamed_video_path.with_suffix(
                ".json"
            )
        )

        video_path.replace(
            renamed_video_path
        )

        if sidecar_path.exists():
            sidecar_path.replace(
                renamed_sidecar_path
            )

        capture_status[
            "output_file"
        ] = str(
            renamed_video_path
        )

        return (
            success,
            message,
            capture_status,
        )

    def _create_sidecar_metadata(
        self,
        *args,
        **kwargs,
    ) -> dict:
        metadata = super()._create_sidecar_metadata(
            *args,
            **kwargs,
        )

        metadata[
            "test"
        ] = {
            "kind":
                "capture_timing",
            "run_id":
                self._timing_run_id,
        }

        return metadata

    def wait_for_capture_writes(
        self,
    ) -> None:
        self._capture_queue.join()

    def write_csv(
        self,
        path: Path,
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=(
                    "sequence_number",
                    "timestamp_utc",
                    "elapsed_seconds",
                    "frame_gap_ms",
                    "callback_ms",
                    "pending_total_ms",
                    "snapshot_ms",
                    "job_build_ms",
                    "queue_ms",
                    "reset_ms",
                    "forced_trigger",
                ),
            )

            writer.writeheader()
            writer.writerows(
                self._timing_rows
            )

    def print_summary(
        self,
    ) -> None:
        gaps = [
            float(
                row[
                    "frame_gap_ms"
                ]
            )
            for row in self._timing_rows
            if row[
                "frame_gap_ms"
            ] != ""
        ]

        callbacks = [
            float(
                row[
                    "callback_ms"
                ]
            )
            for row in self._timing_rows
        ]

        print()
        print("Timing summary")
        print("--------------")
        print(
            f"Frames: {len(self._timing_rows)}"
        )
        print(
            f"Forced captures: {self._timing_trigger_count}"
        )

        if gaps:
            print(
                f"Mean frame gap: {statistics.fmean(gaps):.3f} ms"
            )
            print(
                f"Maximum frame gap: {max(gaps):.3f} ms"
            )

            for threshold in (
                5.0,
                10.0,
                15.0,
                25.0,
                50.0,
            ):
                count = sum(
                    1
                    for gap in gaps
                    if gap > threshold
                )

                print(
                    f"Frame gaps > {threshold:.0f} ms: {count}"
                )

        if callbacks:
            print(
                f"Mean callback: {statistics.fmean(callbacks):.3f} ms"
            )
            print(
                f"Maximum callback: {max(callbacks):.3f} ms"
            )

        pending_rows = [
            row
            for row in self._timing_rows
            if row["pending_total_ms"] != ""
        ]

        if pending_rows:
            print()
            print("Post-trigger handoff timing")
            print("---------------------------")

            for row in pending_rows:
                print(
                    f"t={float(row['elapsed_seconds']):8.3f}s  "
                    f"seq={int(row['sequence_number']):7d}  "
                    f"total={float(row['pending_total_ms']):7.3f} ms  "
                    f"snapshot={float(row['snapshot_ms']):7.3f}  "
                    f"job={float(row['job_build_ms']):7.3f}  "
                    f"queue={float(row['queue_ms']):7.3f}  "
                    f"reset={float(row['reset_ms']):7.3f}"
                )

        worst_rows = sorted(
            (
                row
                for row in self._timing_rows
                if row[
                    "frame_gap_ms"
                ] != ""
            ),
            key=lambda row:
                float(
                    row[
                        "frame_gap_ms"
                    ]
                ),
            reverse=True,
        )[:20]

        if worst_rows:
            print()
            print("Worst 20 frame gaps")
            print("-------------------")

            for row in worst_rows:
                print(
                    f"t={float(row['elapsed_seconds']):8.3f}s  "
                    f"seq={int(row['sequence_number']):7d}  "
                    f"gap={float(row['frame_gap_ms']):8.3f} ms  "
                    f"callback={float(row['callback_ms']):7.3f} ms  "
                    f"forced={row['forced_trigger']}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real Pi capture pipeline with forced automatic captures "
            "and record camera timing."
        )
    )

    parser.add_argument(
        "--seconds",
        type=float,
        default=100.0,
        help="Test duration in seconds (default: 100)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "CSV output path. Default: "
            "camera_timing_YYYYMMDDTHHMMSSZ.csv in current directory"
        ),
    )

    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help=(
            "Optional S3 timing-test run identifier. "
            "Default: current UTC timestamp."
        ),
    )

    arguments = parser.parse_args()

    if arguments.seconds <= 0.0:
        raise RuntimeError("--seconds must be greater than zero")

    stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    run_id = str(
        arguments.run_id or stamp
    ).strip()

    if not run_id:
        raise RuntimeError("--run-id must not be blank")

    if "/" in run_id or "\\" in run_id:
        raise RuntimeError("--run-id must not contain path separators")

    output_path = arguments.output

    if output_path is None:
        output_path = Path(
            f"camera_timing_{run_id}.csv"
        )

    config = CamConfig()

    config.application_start_utc = (
        datetime.now(
            timezone.utc
        ).isoformat(
            timespec="milliseconds"
        ).replace(
            "+00:00",
            "Z",
        )
    )

    event_log = EventLog(
        config
    )

    capture_manager = CaptureManager(
        config,
        event_log,
    )

    trigger_manager = TriggerManager(
        config
    )

    # Prevent ordinary scene content from generating additional triggers.
    # Forced test triggers call BufferManager._arm_pending_trigger() directly.
    trigger_manager.disable()

    manager = TimingBufferManager(
        config,
        trigger_manager,
        event_log,
        capture_manager,
        DEFAULT_TRIGGER_GAPS,
        run_id,
    )

    success, message = manager.start()

    if not success:
        raise RuntimeError(
            f"Unable to start camera: {message}"
        )

    print(
        f"Timing test running for {arguments.seconds:.1f} seconds."
    )
    print(
        "Forced-trigger gaps cycle: "
        + ", ".join(
            f"{value:g}s"
            for value in DEFAULT_TRIGGER_GAPS
        )
    )
    print(
        "First trigger occurs after the first gap; "
        "the gap sequence then repeats for the full test duration."
    )
    print(
        "Leave psf.service running. pcm.service must be stopped."
    )
    print(
        f"Timing-test S3 prefix: test/{run_id}/"
    )

    try:
        deadline = (
            time.monotonic()
            + arguments.seconds
        )

        while (
            time.monotonic()
            < deadline
            and manager.is_running()
        ):
            time.sleep(
                0.25
            )

    finally:
        manager.stop()

    # Let queued CaptureWriter work finish before the process exits.
    manager.wait_for_capture_writes()

    manager.write_csv(
        output_path
    )

    manager.print_summary()

    print()
    print(
        f"CSV: {output_path.resolve()}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
