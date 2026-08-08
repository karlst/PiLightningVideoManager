"""Reject candidates containing sustained brightness-delta noise."""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import CATEGORY_BRIGHT_NOISE
from video_analyzer.solution_types import CATEGORY_TRUE_FLASH
from video_analyzer.solution_types import SolutionResult


class BrightnessNoiseFilter:
    """Reject candidates with noisy brightness-delta behavior."""

    _WINDOW_FRAMES = 100
    _MIN_SIGN_CHANGES = 80

    def __init__(
        self,
        pre_trigger_window_frames: int = 50,
        max_pre_trigger_mean_abs_delta: float = 0.750,
    ) -> None:
        self._pre_trigger_window_frames = int(
            pre_trigger_window_frames
        )

        self._max_pre_trigger_mean_abs_delta = float(
            max_pre_trigger_mean_abs_delta
        )

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        _ = brightness

        pre_trigger_noise = (
            self._get_pre_trigger_mean_absolute_delta(
                brightness_delta,
                trigger_frame_index,
            )
        )

        if (
            pre_trigger_noise is not None
            and pre_trigger_noise
            >= self._max_pre_trigger_mean_abs_delta
        ):
            return SolutionResult(
                is_solution=False,
                category=CATEGORY_BRIGHT_NOISE,
                reason=(
                    "Pre-trigger brightness noise detected: "
                    f"mean |delta| {pre_trigger_noise:.3f} >= "
                    f"{self._max_pre_trigger_mean_abs_delta:.3f} "
                    f"over {self._pre_trigger_window_frames} frames"
                ),
            )

        max_sign_changes = self._find_max_sign_changes(
            brightness_delta
        )

        if max_sign_changes >= self._MIN_SIGN_CHANGES:
            return SolutionResult(
                is_solution=False,
                category=CATEGORY_BRIGHT_NOISE,
                reason=(
                    "Brightness delta oscillation detected: "
                    f"{max_sign_changes} sign changes in "
                    f"{self._WINDOW_FRAMES} frames"
                ),
            )

        return SolutionResult(
            is_solution=True,
            category=CATEGORY_TRUE_FLASH,
            reason="Brightness noise filter passed",
        )

    def _get_pre_trigger_mean_absolute_delta(
        self,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> float | None:
        if trigger_frame_index is None:
            return None

        if trigger_frame_index <= 0:
            return None

        start_index = max(
            0,
            trigger_frame_index -
            self._pre_trigger_window_frames,
        )

        window = brightness_delta[
            start_index:trigger_frame_index
        ]

        if len(window) == 0:
            return None

        return float(
            np.mean(
                np.abs(
                    window
                )
            )
        )

    def _find_max_sign_changes(
        self,
        brightness_delta: np.ndarray,
    ) -> int:
        frame_count = len(brightness_delta)

        if frame_count < self._WINDOW_FRAMES:
            return 0

        max_sign_changes = 0

        for start_index in range(
            0,
            frame_count - self._WINDOW_FRAMES + 1,
        ):
            end_index = (
                start_index +
                self._WINDOW_FRAMES
            )

            window = brightness_delta[
                start_index:end_index
            ]

            sign_changes = 0

            previous_sign = self._get_sign(
                float(window[0])
            )

            for delta in window[1:]:
                current_sign = self._get_sign(
                    float(delta)
                )

                if (
                    previous_sign != 0
                    and current_sign != 0
                    and current_sign != previous_sign
                ):
                    sign_changes += 1

                if current_sign != 0:
                    previous_sign = current_sign

            max_sign_changes = max(
                max_sign_changes,
                sign_changes,
            )

            if max_sign_changes >= self._MIN_SIGN_CHANGES:
                break

        return max_sign_changes

    def _get_sign(
        self,
        value: float,
    ) -> int:
        if value > 0.0:
            return 1

        if value < 0.0:
            return -1

        return 0