"""
@file sidecar_analysis.py

@brief Builds frame records and stored High/Medium/Low replay results for a sidecar.

New sidecars are intended to be self-contained enough that a read-only viewer
can show how the same saved clip behaves under each standard CandidateFinder
sensitivity without rerunning Python analysis.

This module analyzes the raw CameraFrame objects while they are still available
in BufferManager. It performs one sequential pass through the captured frames,
builds the per-frame brightness records, and runs the same shared
CandidateFinder for High, Medium, and Low sensitivity. After CandidateFinder
selects a replay trigger for each sensitivity, the normal SolutionFilter is
run against the complete clip.

The original Pi trigger that caused the clip to be saved remains separate in
the sidecar's "candidate" section. The "sensitivity_results" section is replay
metadata for viewing and comparison; it does not rewrite capture history.
"""

from __future__ import annotations

import cv2
import numpy as np

from common.candidate_config import candidate_config_from_settings
from common.candidate_config import load_candidate_settings
from common.candidate_finder import CandidateFinder
from video_analyzer.solution_config import solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter
from video_analyzer.solution_filter import failed_candidate_result
from video_capture.camera_reader import CameraFrame


SENSITIVITY_NAMES = (
    "high",
    "medium",
    "low",
)


# ## Build sidecar frame records plus replay results for all standard sensitivities.
def analyze_sidecar_frames(
    frames: list[CameraFrame],
) -> tuple[list[dict], dict]:
    settings = load_candidate_settings()

    candidate_configs = {}

    for sensitivity in SENSITIVITY_NAMES:
        sensitivity_settings = dict(
            settings
        )

        sensitivity_settings[
            "sensitivity"
        ] = sensitivity

        candidate_configs[
            sensitivity
        ] = candidate_config_from_settings(
            sensitivity_settings
        )

    candidate_finders = {
        sensitivity:
            CandidateFinder(
                candidate_configs[
                    sensitivity
                ]
            )
        for sensitivity in SENSITIVITY_NAMES
    }

    candidate_frame_indexes: dict[str, int | None] = {
        sensitivity: None
        for sensitivity in SENSITIVITY_NAMES
    }

    candidate_reasons: dict[str, str] = {
        sensitivity: ""
        for sensitivity in SENSITIVITY_NAMES
    }

    frame_records: list[dict] = []
    brightness_values: list[float] = []
    brightness_delta_values: list[float] = []

    previous_gray_frame = None
    previous_mean_brightness: float | None = None
    first_monotonic = 0.0

    if frames:
        first_monotonic = (
            frames[0].timestamp_monotonic
        )

    for frame_index, camera_frame in enumerate(
        frames
    ):
        gray_frame = cv2.cvtColor(
            camera_frame.frame,
            cv2.COLOR_BGR2GRAY
        )

        mean_brightness = float(
            gray_frame.mean()
        )

        brightness_delta_adjacent = 0.0

        if previous_mean_brightness is not None:
            brightness_delta_adjacent = (
                mean_brightness -
                previous_mean_brightness
            )

        positive_delta = None

        if previous_gray_frame is not None:
            positive_delta = cv2.subtract(
                gray_frame,
                previous_gray_frame
            )

        bright_pixel_fraction_by_threshold: dict[float, float] = {}

        for sensitivity in SENSITIVITY_NAMES:
            if candidate_frame_indexes[
                sensitivity
            ] is not None:
                continue

            config = candidate_configs[
                sensitivity
            ]

            bright_pixel_fraction = 0.0

            if positive_delta is not None:
                pixel_delta_threshold = float(
                    config.
                    candidate_bright_pixel_delta_threshold
                )

                if (
                    pixel_delta_threshold
                    not in
                    bright_pixel_fraction_by_threshold
                ):
                    threshold_mask = cv2.compare(
                        positive_delta,
                        pixel_delta_threshold,
                        cv2.CMP_GE
                    )

                    bright_pixel_count = (
                        cv2.countNonZero(
                            threshold_mask
                        )
                    )

                    bright_pixel_fraction_by_threshold[
                        pixel_delta_threshold
                    ] = (
                        float(
                            bright_pixel_count
                        ) /
                        float(
                            positive_delta.size
                        )
                    )

                bright_pixel_fraction = (
                    bright_pixel_fraction_by_threshold[
                        pixel_delta_threshold
                    ]
                )

            metric = {
                "mean_brightness":
                    mean_brightness,

                "brightness_delta_adjacent":
                    brightness_delta_adjacent,

                "bright_pixel_fraction":
                    bright_pixel_fraction,
            }

            found, reason = (
                candidate_finders[
                    sensitivity
                ].evaluate(
                    metric
                )
            )

            if found:
                candidate_frame_indexes[
                    sensitivity
                ] = frame_index

                candidate_reasons[
                    sensitivity
                ] = reason

        offset_ms = (
            (
                camera_frame.timestamp_monotonic -
                first_monotonic
            ) *
            1000.0
        )

        frame_records.append(
            {
                "frame_index":
                    frame_index,

                "sequence_number":
                    camera_frame.sequence_number,

                "timestamp_utc":
                    camera_frame.timestamp_utc,

                "offset_ms":
                    round(
                        offset_ms,
                        3
                    ),

                "mean_brightness":
                    round(
                        mean_brightness,
                        3
                    ),

                "brightness_delta_adjacent":
                    round(
                        brightness_delta_adjacent,
                        3
                    ),
            }
        )

        brightness_values.append(
            mean_brightness
        )

        brightness_delta_values.append(
            brightness_delta_adjacent
        )

        previous_mean_brightness = (
            mean_brightness
        )

        previous_gray_frame = (
            gray_frame
        )

    brightness = np.asarray(
        brightness_values,
        dtype=np.float64
    )

    brightness_delta = np.asarray(
        brightness_delta_values,
        dtype=np.float64
    )

    sensitivity_results: dict[str, dict] = {}

    for sensitivity in SENSITIVITY_NAMES:
        config = candidate_configs[
            sensitivity
        ]

        trigger_frame_index = (
            candidate_frame_indexes[
                sensitivity
            ]
        )

        trigger_reason = (
            candidate_reasons[
                sensitivity
            ]
        )

        if trigger_frame_index is None:
            solution_result = (
                failed_candidate_result()
            )

            solution_reason = (
                "CandidateFinder found no trigger at "
                f"{sensitivity.capitalize()} sensitivity; "
                "SolutionFilter was not run."
            )
        else:
            solution_filter = SolutionFilter(
                solution_config_for_sensitivity(
                    sensitivity
                )
            )

            solution_result = (
                solution_filter.evaluate(
                    brightness,
                    brightness_delta,
                    trigger_frame_index,
                    trigger_reason
                )
            )

            solution_reason = (
                solution_result.reason
            )

        trigger_frame_number = None
        trigger_offset_ms = None

        if trigger_frame_index is not None:
            trigger_frame_number = (
                int(
                    trigger_frame_index
                ) +
                1
            )

            if (
                0 <= trigger_frame_index <
                len(frame_records)
            ):
                trigger_offset_ms = (
                    frame_records[
                        trigger_frame_index
                    ][
                        "offset_ms"
                    ]
                )

        sensitivity_results[
            sensitivity
        ] = {
            "candidate_config":
            {
                "sensitivity":
                    config.sensitivity,

                "candidate_brightness_threshold":
                    config.
                    candidate_brightness_threshold,

                "candidate_brightness_delta_threshold":
                    config.
                    candidate_brightness_delta_threshold,

                "candidate_bright_pixel_delta_threshold":
                    config.
                    candidate_bright_pixel_delta_threshold,

                "candidate_bright_pixel_fraction_threshold":
                    config.
                    candidate_bright_pixel_fraction_threshold,
            },

            "candidate_found":
                trigger_frame_index
                is not None,

            "trigger_frame_index":
                trigger_frame_index,

            "trigger_frame_number":
                trigger_frame_number,

            "trigger_offset_ms":
                trigger_offset_ms,

            "trigger_reason":
                trigger_reason,

            "solution_category":
                solution_result.category,

            "solution_reason":
                solution_reason,
        }

    return (
        frame_records,
        sensitivity_results
    )
