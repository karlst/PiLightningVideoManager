"""Playback-only solution filtering for candidate clips."""

from __future__ import annotations

import numpy as np

from video_analyzer.brightness_noise_filter import BrightnessNoiseFilter
from video_analyzer.frame_dropout_filter import FrameDropoutFilter
from video_analyzer.solution_config import SOLUTION_CONFIG
from video_analyzer.solution_config import SolutionConfig
from video_analyzer.steady_state_change_filter import SteadyStateChangeFilter
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult
from video_analyzer.solution_types import SolutionRule


class SolutionFilter:
    """Run solution filters in sequence until one rejects the candidate."""

    def __init__(
        self,
        config: SolutionConfig = SOLUTION_CONFIG,
    ) -> None:
        self._filters: list[SolutionRule] = [
            BrightnessNoiseFilter(
                pre_trigger_window_frames=(
                    config.pre_trigger_noise_window_frames
                ),
                max_pre_trigger_mean_abs_delta=(
                    config.max_pre_trigger_mean_abs_delta
                ),
            ),
            FrameDropoutFilter(),
            SteadyStateChangeFilter(
                baseline_tolerance=(
                    config.steady_state_baseline_tolerance
                ),
            ),
        ]

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        for solution_filter in self._filters:
            result = solution_filter.evaluate(
                brightness,
                brightness_delta,
                trigger_frame_index,
            )

            if not result.is_solution:
                return result

        return SolutionResult(
            is_solution=True,
            category=CATEGORY_TRUE_FLASH,
            reason="All solution filters passed",
        )