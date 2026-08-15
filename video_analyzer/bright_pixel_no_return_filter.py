"""
Reject bright-pixel Candidates that make a persistent step away from the
pre-trigger brightness trend and do not return.

This filter is intended for bright-pixel Candidates only. It handles scenes
whose background brightness is already drifting, so it does not compare the
post-trigger signal with one fixed baseline value.

Instead it:

1. Estimates the pre-trigger brightness trend from a window before the trigger.
   The estimate uses medians near the beginning and end of the window so a
   short transient inside the window does not strongly distort the trend.

2. Extrapolates that trend through the post-trigger frames.

3. Measures the residual:
       actual brightness - predicted brightness

4. Rejects the Candidate when there is an immediate positive step above the
   expected trend and that offset remains positive through most of the
   following persistence window.

A real transient flash should normally return toward the extrapolated
pre-trigger trend and therefore pass this filter.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import CATEGORY_STEADY_STATE_CHANGE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult


class BrightPixelNoReturnFilter:
    """Reject a bright-pixel trigger that steps upward and stays offset."""

    def __init__(
        self,
        trend_frames: int = 75,
        trend_anchor_frames: int = 10,
        initial_step_frames: int = 6,
        minimum_initial_step: float = 0.35,
        persistence_delay_frames: int = 10,
        persistence_frames: int = 60,
        minimum_persistent_offset: float = 0.25,
        minimum_persistent_fraction: float = 0.80,
    ) -> None:
        self._trend_frames = int(
            trend_frames
        )
        self._trend_anchor_frames = int(
            trend_anchor_frames
        )
        self._initial_step_frames = int(
            initial_step_frames
        )
        self._minimum_initial_step = float(
            minimum_initial_step
        )
        self._persistence_delay_frames = int(
            persistence_delay_frames
        )
        self._persistence_frames = int(
            persistence_frames
        )
        self._minimum_persistent_offset = float(
            minimum_persistent_offset
        )
        self._minimum_persistent_fraction = float(
            minimum_persistent_fraction
        )

    # ## Reject a persistent positive offset from the pre-trigger trend.
    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        del brightness_delta

        details = self._measure_no_return(
            brightness,
            trigger_frame_index,
        )

        if details is None:
            return SolutionResult(
                is_solution=True,
                category=CATEGORY_TRUE_FLASH,
                reason="Bright-pixel no-return filter passed",
            )

        (
            initial_step,
            persistent_median,
            persistent_fraction,
        ) = details

        return SolutionResult(
            is_solution=False,
            category=CATEGORY_STEADY_STATE_CHANGE,
            reason=(
                "Bright-pixel no-return: "
                f"initial offset {initial_step:.3f}, "
                f"persistent median offset {persistent_median:.3f}, "
                f"{persistent_fraction:.0%} of persistence frames "
                f"remain >= {self._minimum_persistent_offset:.3f}"
            ),
        )

    # ## Return diagnostic measurements when the no-return pattern is present.
    def _measure_no_return(
        self,
        brightness: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[float, float, float] | None:
        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness
        )

        if (
            frame_count == 0
            or trigger_frame_index < self._trend_frames
            or trigger_frame_index >= frame_count
        ):
            return None

        anchor_frames = min(
            self._trend_anchor_frames,
            self._trend_frames // 2,
        )

        if anchor_frames < 1:
            return None

        trend_start = (
            trigger_frame_index -
            self._trend_frames
        )

        pre_trigger = brightness[
            trend_start:
            trigger_frame_index
        ]

        if len(pre_trigger) < self._trend_frames:
            return None

        # Estimate the trend from robust endpoint medians instead of fitting all
        # pre-trigger samples. This makes a short spike inside the trend window
        # much less likely to distort the expected post-trigger trajectory.
        start_level = float(
            np.median(
                pre_trigger[
                    :anchor_frames
                ]
            )
        )

        end_level = float(
            np.median(
                pre_trigger[
                    -anchor_frames:
                ]
            )
        )

        start_center = (
            (anchor_frames - 1) /
            2.0
        )

        end_center = (
            self._trend_frames -
            anchor_frames +
            (anchor_frames - 1) /
            2.0
        )

        center_distance = (
            end_center -
            start_center
        )

        if center_distance <= 0.0:
            return None

        slope = (
            end_level -
            start_level
        ) / center_distance

        # The line is anchored at the center of the final pre-trigger anchor.
        def predicted(
            frame_index: int,
        ) -> float:
            local_index = (
                frame_index -
                trend_start
            )

            return (
                end_level +
                slope * (
                    local_index -
                    end_center
                )
            )

        initial_end = min(
            frame_count,
            trigger_frame_index +
            self._initial_step_frames,
        )

        if (
            initial_end -
            trigger_frame_index
            < self._initial_step_frames
        ):
            return None

        initial_residuals = np.asarray(
            [
                float(brightness[index]) -
                predicted(index)
                for index in range(
                    trigger_frame_index,
                    initial_end,
                )
            ],
            dtype=np.float64,
        )

        initial_step = float(
            np.median(
                initial_residuals
            )
        )

        if (
            initial_step <
            self._minimum_initial_step
        ):
            return None

        persistence_start = (
            trigger_frame_index +
            self._persistence_delay_frames
        )

        persistence_end = min(
            frame_count,
            persistence_start +
            self._persistence_frames,
        )

        if (
            persistence_end -
            persistence_start
            < self._persistence_frames
        ):
            return None

        persistent_residuals = np.asarray(
            [
                float(brightness[index]) -
                predicted(index)
                for index in range(
                    persistence_start,
                    persistence_end,
                )
            ],
            dtype=np.float64,
        )

        persistent_median = float(
            np.median(
                persistent_residuals
            )
        )

        persistent_fraction = float(
            np.mean(
                persistent_residuals >=
                self._minimum_persistent_offset
            )
        )

        if (
            persistent_median <
            self._minimum_persistent_offset
        ):
            return None

        if (
            persistent_fraction <
            self._minimum_persistent_fraction
        ):
            return None

        return (
            initial_step,
            persistent_median,
            persistent_fraction,
        )
