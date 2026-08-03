"""Playback-only solution filtering for candidate clips."""

from __future__ import annotations

import numpy as np

from video_analyzer.brightness_noise_filter import BrightnessNoiseFilter
from video_analyzer.frame_dropout_filter import FrameDropoutFilter
from video_analyzer.solution_types import SolutionResult
from video_analyzer.solution_types import SolutionRule


class SolutionFilter:
    """Run solution filters in sequence until one rejects the candidate."""

    def __init__(self) -> None:
        self._filters: list[SolutionRule] = [
            BrightnessNoiseFilter(),
            FrameDropoutFilter(),
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
            reason="All solution filters passed",
        )
